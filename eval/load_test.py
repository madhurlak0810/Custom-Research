#!/usr/bin/env python3
"""
Load test: how does /chat behave as concurrent users increase?

Runs a burst of requests at each concurrency level and reports latency percentiles,
throughput and failures. Failure causes to watch for in this stack:

  504  API Gateway's 29 s integration timeout (slow Bedrock generation)
  429  API Gateway or Lambda throttling
  502  Lambda crashed or returned a malformed response
  200 with no sources / "Error details:"  handler swallowed a DB or Bedrock error

Also pulls Lambda Throttles/Errors/ConcurrentExecutions and Aurora capacity for
the test window, since failures often originate there.

Usage:
  python eval/load_test.py                            # levels 1,5,10,20 x 20 requests
  python eval/load_test.py --levels 1 10 --requests 30
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from common import ask, discover_stack, log, pct, save_results, session
from run_eval import DEFAULT_QUESTIONS


def run_level(api_url, concurrency, n_requests, top_k):
    questions = [DEFAULT_QUESTIONS[i % len(DEFAULT_QUESTIONS)] for i in range(n_requests)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(concurrency) as pool:
        results = list(pool.map(lambda q: ask(api_url, q, top_k=top_k, timeout=35), questions))
    wall = time.perf_counter() - t0

    ok = [r for r in results if r["status"] == 200 and r["sources"] and not r["error"]]
    failures = {}
    for r in results:
        if r in ok:
            continue
        key = str(r["status"]) if r["status"] != 200 else ("200 error" if r["error"] else "200 no sources")
        failures[key] = failures.get(key, 0) + 1
    lat = [r["latency_s"] for r in ok]
    return {
        "concurrency": concurrency,
        "requests": n_requests,
        "success_rate": round(len(ok) / n_requests, 3),
        "throughput_rps": round(n_requests / wall, 2),
        "p50_s": pct(lat, 50),
        "p90_s": pct(lat, 90),
        "p99_s": pct(lat, 99),
        "max_s": max(lat) if lat else None,
        "failures": failures,
        "sample_errors": list({r["error"][:150] for r in results if r["error"]})[:3],
    }


def cloudwatch_summary(cw, stack, start, end):
    def stat(namespace, metric, dims, statistic):
        pts = cw.get_metric_statistics(Namespace=namespace, MetricName=metric, Dimensions=dims,
                                       StartTime=start, EndTime=end, Period=60, Statistics=[statistic])
        vals = [p[statistic] for p in pts["Datapoints"]]
        if not vals:
            return None
        return sum(vals) if statistic == "Sum" else max(vals)

    fn = [{"Name": "FunctionName", "Value": stack["chat_fn"]}]
    db = [{"Name": "DBClusterIdentifier", "Value": stack["db_cluster"]}]
    return {
        "lambda_invocations": stat("AWS/Lambda", "Invocations", fn, "Sum"),
        "lambda_errors": stat("AWS/Lambda", "Errors", fn, "Sum"),
        "lambda_throttles": stat("AWS/Lambda", "Throttles", fn, "Sum"),
        "lambda_max_concurrency": stat("AWS/Lambda", "ConcurrentExecutions", fn, "Maximum"),
        "aurora_max_acu": stat("AWS/RDS", "ServerlessDatabaseCapacity", db, "Maximum"),
        "aurora_max_connections": stat("AWS/RDS", "DatabaseConnections", db, "Maximum"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 5, 10, 20])
    ap.add_argument("--requests", type=int, default=20, help="requests per level")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--pause", type=int, default=10, help="seconds between levels")
    args = ap.parse_args()

    sess = session()
    stack = discover_stack(sess.client("cloudformation"))
    start = datetime.now(timezone.utc)
    levels = []
    for i, c in enumerate(args.levels):
        if i:
            time.sleep(args.pause)
        log(f"Concurrency {c}: {args.requests} requests...")
        levels.append(run_level(stack["api_url"], c, args.requests, args.top_k))
        lv = levels[-1]
        log(f"  success {lv['success_rate']:.0%}, p50 {lv['p50_s']} s, p90 {lv['p90_s']} s, "
            f"{lv['throughput_rps']} req/s, failures {lv['failures'] or 'none'}")
    end = datetime.now(timezone.utc)

    log("Waiting 90 s for CloudWatch metrics...")
    time.sleep(90)
    cw = cloudwatch_summary(sess.client("cloudwatch"), stack,
                            start.replace(second=0, microsecond=0), end + timedelta(minutes=2))

    out = save_results("load-test", {"levels": levels, "cloudwatch": cw})
    print(f"\nLoad test on /chat ({args.requests} requests per level)")
    print(f"{'concurrency':>11}{'success':>9}{'req/s':>8}{'p50':>8}{'p90':>8}{'p99':>8}  failures")
    for lv in levels:
        f = ", ".join(f"{k}: {v}" for k, v in lv["failures"].items()) or "-"
        fmt = lambda v: f"{v:.1f}s" if v is not None else "n/a"  # noqa: E731
        print(f"{lv['concurrency']:>11}{lv['success_rate']:>9.0%}{lv['throughput_rps']:>8}"
              f"{fmt(lv['p50_s']):>8}{fmt(lv['p90_s']):>8}{fmt(lv['p99_s']):>8}  {f}")
    print("\nCloudWatch during the test: " + ", ".join(f"{k}={v}" for k, v in cw.items()))
    for lv in levels:
        for e in lv["sample_errors"]:
            print(f"  error at concurrency {lv['concurrency']}: {e}")
    print(f"Full results: {out}")


if __name__ == "__main__":
    main()
