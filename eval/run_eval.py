#!/usr/bin/env python3
"""
End-to-end evaluation of the deployed ServerlessRagStack.

Produces the four "By the numbers" figures:
  - Papers indexed          (sum of newly inserted papers from the ingest phase,
                             or a CloudWatch Logs count when ingestion is skipped)
  - Median answer time      (wall-clock POST /chat through API Gateway)
  - Ingestion per paper     (ingest Lambda duration / papers inserted, invoked
                             directly so API Gateway's 29 s limit doesn't apply)
  - Cost per day            (fixed infra + measured per-query cost x daily volume)

Usage:
  pip install -r eval/requirements.txt
  python eval/run_eval.py                       # full run: ingest + chat + cost
  python eval/run_eval.py --skip-ingest         # re-measure chat/cost only
  python eval/run_eval.py --topics "graph neural networks" --papers-per-topic 5

Requires AWS credentials allowed to: cloudformation:DescribeStack*,
lambda:InvokeFunction, cloudwatch:GetMetricStatistics, logs:StartQuery/GetQueryResults.
"""

import argparse
import base64
import json
import re
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import STACK_NAME, discover_stack, log, pct, post_json, session

EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
CHAT_MODEL = "openai.gpt-oss-20b-1:0"

# us-east-1 on-demand list prices (USD). Verify against current AWS pricing before publishing.
PRICE = {
    "nat_gateway_hour": 0.045,
    "aurora_acu_hour": 0.12,          # Aurora Serverless v2, Standard config
    "ec2_t3_micro_hour": 0.0104,      # Chat UI instance
    "public_ipv4_hour": 0.005,        # per address: NAT EIP + Chat UI instance
    "secret_month": 0.40,             # Secrets Manager, DB credentials
    "lambda_gb_second": 0.0000166667,
    "lambda_request": 0.20 / 1e6,
    "apigw_request": 3.50 / 1e6,
    "titan_embed_1k_tokens": 0.00002,
    "chat_input_1k_tokens": 0.00007,  # gpt-oss-20b
    "chat_output_1k_tokens": 0.0003,
}
PUBLIC_IPV4_COUNT = 2
CHAT_LAMBDA_GB = 0.5  # memorySize: 512 in serverless-rag-stack.ts

DEFAULT_TOPICS = [
    "retrieval augmented generation",
    "large language models",
    "diffusion models",
    "reinforcement learning from human feedback",
    "graph neural networks",
    "quantum machine learning",
]

DEFAULT_QUESTIONS = [
    "What are recent developments in retrieval augmented generation?",
    "How do large language models handle long context?",
    "What techniques reduce hallucination in language models?",
    "How are diffusion models used for image generation?",
    "What are the main challenges of RLHF?",
    "How do graph neural networks scale to large graphs?",
    "What problems is quantum machine learning expected to speed up?",
    "Which evaluation benchmarks are commonly used for LLMs?",
    "How is reward modeling done in reinforcement learning from human feedback?",
    "What are the trade-offs between fine-tuning and retrieval for domain adaptation?",
]


# ---------------------------------------------------------------- ingest phase

DURATION_RE = re.compile(r"REPORT RequestId.*?\tDuration: ([\d.]+) ms")
INIT_RE = re.compile(r"Init Duration: ([\d.]+) ms")


def run_ingest(lam, fn_name, topics, per_topic):
    rows = []
    for i, topic in enumerate(topics):
        if i:
            time.sleep(3)  # arXiv API asks for >= 3 s between requests
        payload = {"body": json.dumps({"query": topic, "max_results": per_topic})}
        t0 = time.perf_counter()
        resp = lam.invoke(FunctionName=fn_name, Payload=json.dumps(payload), LogType="Tail")
        wall = time.perf_counter() - t0
        result = json.loads(resp["Payload"].read() or "{}")
        body = json.loads(result.get("body") or "{}")
        tail = base64.b64decode(resp.get("LogResult", "")).decode(errors="replace")
        m, mi = DURATION_RE.search(tail), INIT_RE.search(tail)
        duration_s = float(m.group(1)) / 1000 if m else wall
        init_s = float(mi.group(1)) / 1000 if mi else 0.0
        inserted = body.get("processed_count", 0)
        row = {
            "topic": topic,
            "status": result.get("statusCode"),
            "fetched": body.get("total_papers_fetched", 0),
            "inserted": inserted,
            "database_enabled": body.get("database_enabled"),
            "lambda_duration_s": round(duration_s, 3),
            "cold_start_init_s": round(init_s, 3),
            "wall_s": round(wall, 3),
            "per_paper_s": round(duration_s / inserted, 3) if inserted else None,
            "error": body.get("error") or body.get("database_error") or resp.get("FunctionError"),
        }
        rows.append(row)
        log(f"  ingest '{topic}': status={row['status']} inserted={inserted}/{row['fetched']} "
            f"duration={duration_s:.1f}s" + (f"  ERROR: {row['error']}" if row["error"] else ""))
    return rows


def count_papers_from_logs(logs, fn_name, days=7):
    """Fallback when ingestion is skipped: count distinct inserts still within log retention."""
    now = int(time.time())
    q = logs.start_query(
        logGroupName=f"/aws/lambda/{fn_name}",
        startTime=now - days * 86400, endTime=now,
        queryString='filter @message like /Successfully processed paper/ '
                    '| parse @message "Successfully processed paper: *" as arxiv_id '
                    '| stats count_distinct(arxiv_id) as n',
    )["queryId"]
    for _ in range(60):
        res = logs.get_query_results(queryId=q)
        if res["status"] in ("Complete", "Failed", "Cancelled"):
            break
        time.sleep(1)
    if res["status"] != "Complete" or not res["results"]:
        return None
    return int({f["field"]: f["value"] for f in res["results"][0]}["n"])


# ---------------------------------------------------------------- chat phase

def run_chat(api_url, questions, repeats, top_k):
    rows = []
    for rep in range(repeats):
        for q in questions:
            status, text, elapsed = post_json(f"{api_url}/chat", {"query": q, "top_k": top_k})
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = {"error": text[:200]}
            answer = body.get("response") or ""
            sources = body.get("sources") or []
            # The handler's "similarity" field is pgvector's <=> cosine *distance*: lower is closer.
            distances = [s["similarity"] for s in sources if "similarity" in s]
            ok = status == 200 and bool(sources) and not answer.startswith("Error details:")
            rows.append({
                "question": q,
                "repeat": rep,
                "status": status,
                "ok": ok,
                "latency_s": round(elapsed, 3),
                "n_sources": len(sources),
                "best_cosine_distance": min(distances) if distances else None,
                "answer_chars": len(answer),
                "error": body.get("error") or (answer if answer.startswith("Error details:") else None),
            })
            log(f"  chat [{len(rows)}]: status={status} {elapsed:.2f}s sources={len(sources)}"
                + ("" if ok else f"  FAILED: {(rows[-1]['error'] or 'no sources')[:120]}"))
    return rows


# ---------------------------------------------------------------- cost

def metric_sum(cw, namespace, metric, dims, start, end, stat="Sum"):
    pts = cw.get_metric_statistics(Namespace=namespace, MetricName=metric, Dimensions=dims,
                                   StartTime=start, EndTime=end, Period=60, Statistics=[stat])
    vals = [p[stat] for p in pts["Datapoints"]]
    if not vals:
        return None
    return sum(vals) if stat == "Sum" else statistics.mean(vals)


def bedrock_tokens(cw, model_id, start, end, wait_s):
    """Bedrock CloudWatch metrics land a few minutes late; poll until they appear."""
    dims = [{"Name": "ModelId", "Value": model_id}]
    deadline = time.time() + wait_s
    while True:
        tin = metric_sum(cw, "AWS/Bedrock", "InputTokenCount", dims, start, end)
        tout = metric_sum(cw, "AWS/Bedrock", "OutputTokenCount", dims, start, end)
        if tin is not None or time.time() >= deadline:
            return tin, tout
        time.sleep(15)


def estimate_cost(cw, stack, chat_rows, chat_start, chat_end, queries_per_day, top_k, wait_s):
    now = datetime.now(timezone.utc)
    acu = metric_sum(cw, "AWS/RDS", "ServerlessDatabaseCapacity",
                     [{"Name": "DBClusterIdentifier", "Value": stack["db_cluster"]}],
                     now - timedelta(hours=24), now, stat="Average") if stack["db_cluster"] else None
    acu_source = "CloudWatch 24h average"
    if acu is None:
        acu, acu_source = 0.5, "assumed serverlessV2MinCapacity"

    fixed = {
        "nat_gateway": PRICE["nat_gateway_hour"] * 24,
        "aurora_compute": PRICE["aurora_acu_hour"] * acu * 24,
        "chat_ui_ec2": PRICE["ec2_t3_micro_hour"] * 24,
        "public_ipv4": PRICE["public_ipv4_hour"] * PUBLIC_IPV4_COUNT * 24,
        "secrets_manager": PRICE["secret_month"] / 30,
    }

    n = len(chat_rows) or 1
    # Metrics are per-minute buckets; widen the window so partial minutes are included.
    w_start = chat_start.replace(second=0, microsecond=0)
    w_end = chat_end + timedelta(minutes=1)
    log(f"  waiting up to {wait_s}s for Bedrock token metrics...")
    chat_in, chat_out = bedrock_tokens(cw, CHAT_MODEL, w_start, w_end, wait_s)
    emb_in, _ = bedrock_tokens(cw, EMBEDDING_MODEL, w_start, w_end, 0)
    if chat_in is not None:
        token_source = "CloudWatch AWS/Bedrock"
    else:
        # ~300 tokens per arXiv abstract in context, ~4 chars per output token
        chat_in = n * (top_k * 300 + 100)
        chat_out = sum(r["answer_chars"] for r in chat_rows) / 4
        emb_in = n * 20
        token_source = "estimated (Bedrock metrics unavailable)"

    lam_s = metric_sum(cw, "AWS/Lambda", "Duration",
                       [{"Name": "FunctionName", "Value": stack["chat_fn"]}], w_start, w_end)
    lam_s = lam_s / 1000 if lam_s is not None else sum(r["latency_s"] for r in chat_rows)

    per_query = (
        (chat_in or 0) / 1000 * PRICE["chat_input_1k_tokens"]
        + (chat_out or 0) / 1000 * PRICE["chat_output_1k_tokens"]
        + (emb_in or 0) / 1000 * PRICE["titan_embed_1k_tokens"]
        + lam_s * CHAT_LAMBDA_GB * PRICE["lambda_gb_second"]
        + n * (PRICE["lambda_request"] + PRICE["apigw_request"])
    ) / n

    fixed_total = sum(fixed.values())
    return {
        "fixed_per_day": {k: round(v, 4) for k, v in fixed.items()},
        "fixed_total_per_day": round(fixed_total, 2),
        "aurora_avg_acu": round(acu, 3),
        "aurora_acu_source": acu_source,
        "per_query_usd": round(per_query, 6),
        "token_source": token_source,
        "tokens_per_query": {"chat_in": round((chat_in or 0) / n), "chat_out": round((chat_out or 0) / n)},
        "queries_per_day_assumed": queries_per_day,
        "total_per_day": round(fixed_total + per_query * queries_per_day, 2),
    }


# ---------------------------------------------------------------- report

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", nargs="+", default=DEFAULT_TOPICS)
    ap.add_argument("--papers-per-topic", type=int, default=10)
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--questions-file", help="JSON list of question strings")
    ap.add_argument("--repeats", type=int, default=2, help="passes over the question set")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--queries-per-day", type=int, default=100, help="volume assumed for cost/day")
    ap.add_argument("--metrics-wait", type=int, default=240, help="seconds to wait for Bedrock metrics")
    ap.add_argument("--label", default=datetime.now().strftime("%B %Y redeploy"))
    ap.add_argument("--out-dir", default=str(Path(__file__).parent / "results"))
    args = ap.parse_args()

    sess = session()
    cfn, lam, cw, logs = (sess.client(s) for s in ("cloudformation", "lambda", "cloudwatch", "logs"))

    log(f"Discovering stack {STACK_NAME}...")
    stack = discover_stack(cfn)
    log(f"  API: {stack['api_url']}")

    ingest_rows = []
    if not args.skip_ingest:
        log(f"Ingest phase: {len(args.topics)} topics x {args.papers_per_topic} papers")
        ingest_rows = run_ingest(lam, stack["ingest_fn"], args.topics, args.papers_per_topic)
        papers_indexed = sum(r["inserted"] for r in ingest_rows)
        papers_source = "inserted during this run"
    else:
        papers_indexed = count_papers_from_logs(logs, stack["ingest_fn"])
        papers_source = "distinct inserts in ingest logs (7-day retention)"

    questions = json.loads(Path(args.questions_file).read_text()) if args.questions_file else DEFAULT_QUESTIONS
    log(f"Chat phase: {len(questions)} questions x {args.repeats}")
    chat_start = datetime.now(timezone.utc)
    chat_rows = run_chat(stack["api_url"], questions, args.repeats, args.top_k)
    chat_end = datetime.now(timezone.utc)

    log("Cost phase")
    cost = estimate_cost(cw, stack, chat_rows, chat_start, chat_end,
                         args.queries_per_day, args.top_k, args.metrics_wait)

    ok_lat = [r["latency_s"] for r in chat_rows if r["ok"]]
    warm_lat = [r["latency_s"] for r in chat_rows[1:] if r["ok"]]
    per_paper = [r["per_paper_s"] for r in ingest_rows if r["per_paper_s"]]
    dists = [r["best_cosine_distance"] for r in chat_rows if r["best_cosine_distance"] is not None]

    summary = {
        "label": args.label,
        "timestamp": chat_end.isoformat(),
        "papers_indexed": papers_indexed,
        "papers_indexed_source": papers_source,
        "chat": {
            "requests": len(chat_rows),
            "success_rate": round(len(ok_lat) / len(chat_rows), 3) if chat_rows else None,
            "median_s": pct(ok_lat, 50),
            "p90_s": pct(ok_lat, 90),
            "warm_median_s": pct(warm_lat, 50),
            "first_request_s": chat_rows[0]["latency_s"] if chat_rows else None,
            "median_best_cosine_distance": pct(dists, 50),
        },
        "ingest": {
            "requests": len(ingest_rows),
            "median_per_paper_s": pct(per_paper, 50),
            "total_inserted": sum(r["inserted"] for r in ingest_rows),
            "total_lambda_s": round(sum(r["lambda_duration_s"] for r in ingest_rows), 1),
        },
        "cost": cost,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"eval-{chat_end.strftime('%Y%m%dT%H%M%SZ')}.json"
    out_file.write_text(json.dumps({"summary": summary, "ingest": ingest_rows, "chat": chat_rows}, indent=2))

    def fmt(v, unit=""):
        return "n/a" if v is None else f"{v:.1f}{unit}" if isinstance(v, float) else f"{v}{unit}"

    print(f"""
By the numbers
{fmt(papers_indexed)}
Papers indexed
{fmt(summary['chat']['median_s'], ' s')}
Median answer time
{fmt(summary['ingest']['median_per_paper_s'], ' s')}
Ingestion per paper
${cost['total_per_day']:.2f}
Cost per day to run
Measured on the {args.label}
""")
    c = summary["chat"]
    print(f"Details: chat success {fmt(c['success_rate'])}, p90 {fmt(c['p90_s'], ' s')}, "
          f"warm median {fmt(c['warm_median_s'], ' s')}, first request {fmt(c['first_request_s'], ' s')}")
    print(f"         cost = ${cost['fixed_total_per_day']:.2f}/day fixed + ${cost['per_query_usd']:.5f}/query "
          f"x {args.queries_per_day} queries/day (tokens: {cost['token_source']}; ACU: {cost['aurora_acu_source']})")
    print(f"         papers indexed: {papers_source}")
    print(f"Full results: {out_file}")


if __name__ == "__main__":
    main()
