#!/usr/bin/env python3
"""
Retrieval accuracy: when you ask about a specific indexed paper, does search return it?

Builds a gold set from the same arXiv queries the ingest phase used (cached in
eval/datasets/retrieval_gold.json so later runs compare like with like), then for
each paper sends two queries through POST /chat and checks where that paper lands
in the returned sources:

  title     - the paper's title (easy: near-duplicate of the embedded text)
  sentence  - the second sentence of its abstract (harder: a partial description)

Reports hit@1, hit@k and MRR per query type and per topic.

Usage:
  python eval/retrieval_eval.py                    # build gold set if missing, then evaluate
  python eval/retrieval_eval.py --rebuild-gold     # re-fetch from arXiv first
  python eval/retrieval_eval.py --limit 20         # quick run on 20 papers
"""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from common import DATASETS_DIR, ask, arxiv_search, discover_stack, log, pct, save_results, session
from run_eval import DEFAULT_TOPICS

GOLD_FILE = DATASETS_DIR / "retrieval_gold.json"


def build_gold(topics, per_topic):
    gold = []
    for i, topic in enumerate(topics):
        if i:
            time.sleep(3)  # arXiv API asks for >= 3 s between requests
        for p in arxiv_search(topic, per_topic):
            sentences = re.split(r"(?<=[.!?])\s+", p["abstract"])
            gold.append({
                "topic": topic,
                "arxiv_id": p["arxiv_id"],
                "title": p["title"],
                "sentence": sentences[1] if len(sentences) > 1 else sentences[0],
            })
        log(f"  gold: '{topic}' -> {len(gold)} papers so far")
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_FILE.write_text(json.dumps(gold, indent=2))
    return gold


def evaluate_one(api_url, item, query_type, top_k):
    r = ask(api_url, item[query_type], top_k=top_k)
    ids = [s.get("arxiv_id") for s in r["sources"]]
    rank = ids.index(item["arxiv_id"]) + 1 if item["arxiv_id"] in ids else None
    return {
        "topic": item["topic"],
        "arxiv_id": item["arxiv_id"],
        "query_type": query_type,
        "query": item[query_type],
        "status": r["status"],
        "rank": rank,
        "returned": ids,
        "latency_s": r["latency_s"],
        "error": r["error"],
    }


def summarize(rows, top_k):
    ok = [r for r in rows if r["status"] == 200 and not r["error"]]
    if not ok:
        return {"n": 0, "errors": len(rows)}
    return {
        "n": len(ok),
        "errors": len(rows) - len(ok),
        "hit@1": round(sum(r["rank"] == 1 for r in ok) / len(ok), 3),
        f"hit@{top_k}": round(sum(r["rank"] is not None for r in ok) / len(ok), 3),
        "mrr": round(sum(1 / r["rank"] for r in ok if r["rank"]) / len(ok), 3),
        "median_latency_s": pct([r["latency_s"] for r in ok], 50),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", nargs="+", default=DEFAULT_TOPICS)
    ap.add_argument("--papers-per-topic", type=int, default=10)
    ap.add_argument("--rebuild-gold", action="store_true")
    ap.add_argument("--limit", type=int, help="evaluate only the first N gold papers")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--workers", type=int, default=6, help="concurrent /chat requests")
    args = ap.parse_args()

    if args.rebuild_gold or not GOLD_FILE.exists():
        log("Building gold set from arXiv...")
        gold = build_gold(args.topics, args.papers_per_topic)
    else:
        gold = json.loads(GOLD_FILE.read_text())
    gold = gold[: args.limit] if args.limit else gold

    stack = discover_stack(session().client("cloudformation"))
    jobs = [(item, qt) for item in gold for qt in ("title", "sentence")]
    log(f"Evaluating {len(gold)} papers x 2 query types ({len(jobs)} requests, {args.workers} workers)...")
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda j: evaluate_one(stack["api_url"], j[0], j[1], args.top_k), jobs))

    by_type = {qt: summarize([r for r in rows if r["query_type"] == qt], args.top_k) for qt in ("title", "sentence")}
    by_topic = {t: summarize([r for r in rows if r["topic"] == t], args.top_k) for t in dict.fromkeys(g["topic"] for g in gold)}
    misses = [r for r in rows if r["status"] == 200 and not r["error"] and r["rank"] is None]

    out = save_results("retrieval", {"summary": {"by_query_type": by_type, "by_topic": by_topic},
                                     "top_k": args.top_k, "rows": rows})

    k = f"hit@{args.top_k}"
    print(f"\nRetrieval accuracy ({len(gold)} papers, top_k={args.top_k})")
    print(f"{'':<34}{'n':>4}{'hit@1':>8}{k:>8}{'MRR':>7}")
    for name, s in [*by_type.items(), ("", None), *by_topic.items()]:
        if s is None:
            print("  by topic:")
            continue
        if not s.get("n"):
            print(f"  {name[:32]:<32}  all {s['errors']} requests failed")
            continue
        print(f"  {name[:32]:<32}{s['n']:>4}{s['hit@1']:>8.2f}{s[k]:>8.2f}{s['mrr']:>7.2f}")
    errors = sum(1 for r in rows if r["status"] != 200 or r["error"])
    print(f"\nMissed entirely: {len(misses)}   request errors: {errors}")
    for r in misses[:5]:
        print(f"  miss [{r['query_type']}] {r['arxiv_id']}: {r['query'][:80]}")
    print(f"Full results: {out}")


if __name__ == "__main__":
    main()
