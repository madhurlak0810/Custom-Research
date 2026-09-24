#!/usr/bin/env python3
"""
Answer quality: are the chat answers faithful to the papers they cite, and do they answer the question?

For each question, calls POST /chat, fetches the abstracts of the returned sources
from arXiv (the same text the chat Lambda put in its prompt), and asks Claude Opus 5
on Bedrock to grade the answer against them:

  faithfulness (1-5)  every claim is supported by the source abstracts
  relevance    (1-5)  the answer addresses the question that was asked
  unsupported_claims  claims in the answer the sources don't back up

Requires Anthropic model access on Bedrock (Bedrock console -> Model access).

Usage:
  pip install -r eval/requirements.txt
  python eval/answer_quality_eval.py
  python eval/answer_quality_eval.py --questions-file my_questions.json
"""

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import List

import anthropic
from anthropic import AnthropicBedrockMantle
from pydantic import BaseModel

from common import REGION, arxiv_by_ids, ask, discover_stack, log, pct, save_results, session
from run_eval import DEFAULT_QUESTIONS

JUDGE_MODEL = "anthropic.claude-opus-5"

JUDGE_PROMPT = """You are grading one answer from a research-paper question-answering system.
The system retrieved the paper abstracts below and wrote the answer from them.

Grade two things:

faithfulness (1-5): Is every factual claim in the answer supported by the abstracts?
  5 = all claims supported; 3 = some claims go beyond the abstracts; 1 = mostly unsupported or contradicts them.
  General background knowledge that is uncontroversial (e.g. "transformers use attention") does not count against it,
  but specific results, numbers, method names or paper attributions must come from the abstracts.

relevance (1-5): Does the answer address the question that was asked?
  5 = directly and completely; 3 = partially or padded with off-topic material; 1 = does not address it.

List each unsupported claim verbatim or near-verbatim in unsupported_claims (empty list if none).
If the abstracts genuinely don't cover the question, an answer that says so is faithful and relevant.

<question>
{question}
</question>

<abstracts>
{abstracts}
</abstracts>

<answer>
{answer}
</answer>"""


class Grade(BaseModel):
    faithfulness: int
    relevance: int
    unsupported_claims: List[str]
    reasoning: str


def judge(client, question, answer, papers):
    abstracts = "\n\n".join(
        f"[{p['arxiv_id']}] {p['title']}\n{p['abstract']}" for p in papers
    ) or "(no sources were retrieved)"
    response = client.messages.parse(
        model=JUDGE_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            question=question, abstracts=abstracts, answer=answer)}],
        output_format=Grade,
    )
    if response.stop_reason == "refusal":
        return None, "judge refused"
    return response.parsed_output, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions-file", help="JSON list of question strings")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    questions = json.loads(open(args.questions_file).read()) if args.questions_file else DEFAULT_QUESTIONS
    stack = discover_stack(session().client("cloudformation"))
    client = AnthropicBedrockMantle(aws_region=REGION)
    try:  # fail before spending on /chat calls if the judge isn't reachable
        client.messages.create(model=JUDGE_MODEL, max_tokens=256,
                               messages=[{"role": "user", "content": "Reply with OK."}])
    except anthropic.PermissionDeniedError as e:
        raise SystemExit(f"Judge model {JUDGE_MODEL} is not available: {e.message}\n"
                         "Enable Anthropic model access in the Bedrock console (Model access) and retry.")

    log(f"Asking {len(questions)} questions...")
    with ThreadPoolExecutor(args.workers) as pool:
        answers = list(pool.map(lambda q: ask(stack["api_url"], q, top_k=args.top_k), questions))

    log("Fetching source abstracts from arXiv...")
    abstracts = arxiv_by_ids([s["arxiv_id"] for a in answers for s in a["sources"]])

    def grade(pair):
        q, a = pair
        row = {"question": q, "status": a["status"], "latency_s": a["latency_s"],
               "answer": a["answer"], "sources": [s["arxiv_id"] for s in a["sources"]]}
        if a["status"] != 200 or a["error"]:
            return {**row, "error": a["error"] or f"HTTP {a['status']}"}
        papers = [abstracts[s["arxiv_id"]] for s in a["sources"] if s["arxiv_id"] in abstracts]
        try:
            g, err = judge(client, q, a["answer"], papers)
        except anthropic.APIStatusError as e:
            return {**row, "error": f"judge HTTP {e.status_code}: {e.message}"}
        if err:
            return {**row, "error": err}
        log(f"  graded: faithfulness={g.faithfulness} relevance={g.relevance} "
            f"unsupported={len(g.unsupported_claims)}  {q[:60]}")
        return {**row, **g.model_dump(), "error": None}

    log(f"Grading with {JUDGE_MODEL}...")
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(grade, zip(questions, answers)))

    graded = [r for r in rows if not r["error"]]
    summary = {
        "judge_model": JUDGE_MODEL,
        "questions": len(rows),
        "graded": len(graded),
        "mean_faithfulness": round(statistics.mean(r["faithfulness"] for r in graded), 2) if graded else None,
        "mean_relevance": round(statistics.mean(r["relevance"] for r in graded), 2) if graded else None,
        "fully_faithful_rate": round(sum(r["faithfulness"] == 5 for r in graded) / len(graded), 3) if graded else None,
        "answers_with_unsupported_claims": sum(bool(r["unsupported_claims"]) for r in graded),
        "median_answer_chars": pct([len(r["answer"]) for r in graded], 50),
    }
    out = save_results("answer-quality", {"summary": summary, "rows": rows})

    print(f"\nAnswer quality ({summary['graded']}/{summary['questions']} graded by {JUDGE_MODEL})")
    if graded:
        print(f"  faithfulness  {summary['mean_faithfulness']}/5   (fully faithful: {summary['fully_faithful_rate']:.0%})")
        print(f"  relevance     {summary['mean_relevance']}/5")
        print(f"  answers with unsupported claims: {summary['answers_with_unsupported_claims']}")
        worst = sorted(graded, key=lambda r: (r["faithfulness"], r["relevance"]))[:3]
        for r in worst:
            print(f"  lowest: F={r['faithfulness']} R={r['relevance']}  {r['question'][:70]}")
            for c in r["unsupported_claims"][:2]:
                print(f"          unsupported: {c[:110]}")
    for r in rows:
        if r["error"]:
            print(f"  not graded: {r['question'][:60]}  ({r['error'][:120]})")
    print(f"Full results: {out}")


if __name__ == "__main__":
    main()
