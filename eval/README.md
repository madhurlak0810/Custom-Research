# Evaluations

Scripts that measure the deployed `ServerlessRagStack` in `us-east-1`. Each one finds the API and resources from CloudFormation, prints a summary, and writes full per-request results to `eval/results/<name>-<timestamp>.json`.

```
pip install -r eval/requirements.txt
```

| Script | Question it answers | Requests | Writes data? |
|---|---|---|---|
| `run_eval.py` | The headline numbers: papers indexed, median answer time, ingestion per paper, cost per day | 6 ingests + 20 chats | Yes, ingests 60 papers (`--skip-ingest` to avoid) |
| `retrieval_eval.py` | When you ask about a specific indexed paper, does search return it? (hit@1, hit@k, MRR) | 2 per gold paper (120 by default) | No |
| `answer_quality_eval.py` | Are answers faithful to the cited abstracts and relevant to the question? Graded by Claude Opus 5 on Bedrock | 10 chats + 10 judge calls | No |
| `load_test.py` | How latency, throughput and errors change with concurrent users | 20 per concurrency level (80 by default) | No |
| `edge_cases.py` | Does the API handle bad, hostile or out-of-scope input sensibly? | 16 | No |

## Notes

- **Credentials:** any AWS credentials that can read CloudFormation and CloudWatch, invoke the ingest Lambda (`run_eval.py`), and call Bedrock (`answer_quality_eval.py`).
- **Judge access:** `answer_quality_eval.py` needs Anthropic model access enabled for the account in the Bedrock console. It checks this before making any `/chat` calls and exits with a message if access is missing.
- **Gold set:** `retrieval_eval.py` caches its gold set in `eval/datasets/retrieval_gold.json`. It is built from the same arXiv queries the ingest step uses, so it only matches what's indexed if those topics were ingested (`run_eval.py` does this). Use `--rebuild-gold` after re-ingesting.
- **Cost figures:** `run_eval.py` uses list prices hardcoded in its `PRICE` table. Check them against current AWS pricing before publishing.
- **Time:** every `/chat` call runs the full RAG pipeline, including answer generation (about 8 s), so the retrieval and load tests use concurrent workers.
