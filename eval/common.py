"""Shared helpers for the evaluation scripts in this folder."""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import boto3

REGION = "us-east-1"
STACK_NAME = "ServerlessRagStack"
RESULTS_DIR = Path(__file__).parent / "results"
DATASETS_DIR = Path(__file__).parent / "datasets"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def session():
    return boto3.Session(region_name=REGION)


def discover_stack(cfn):
    stack = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    resources = cfn.describe_stack_resources(StackName=STACK_NAME)["StackResources"]

    def physical(prefix, rtype):
        for r in resources:
            if r["ResourceType"] == rtype and r["LogicalResourceId"].startswith(prefix):
                return r["PhysicalResourceId"]
        return None

    return {
        "api_url": outputs["ApiEndpoint"].rstrip("/"),
        "ingest_fn": physical("IngestFunction", "AWS::Lambda::Function"),
        "chat_fn": physical("ChatFunction", "AWS::Lambda::Function"),
        "db_cluster": physical("RagDatabase", "AWS::RDS::DBCluster"),
    }


def request(url, body=None, method="POST", raw_body=None, headers=None, timeout=60):
    """Returns (status, text, elapsed_s). status is None on network errors/timeouts."""
    data = raw_body.encode() if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, text = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        status, text = None, str(e)
    return status, text, time.perf_counter() - t0


def post_json(url, body, timeout=60):
    return request(url, body, timeout=timeout)


def parse_json(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"error": (text or "")[:300]}


def ask(api_url, query, top_k=5, timeout=60, **extra):
    """POST /chat and return a flat result dict."""
    status, text, elapsed = post_json(f"{api_url}/chat", {"query": query, "top_k": top_k, **extra}, timeout)
    body = parse_json(text)
    answer = body.get("response") or ""
    return {
        "status": status,
        "latency_s": round(elapsed, 3),
        "answer": answer,
        "sources": body.get("sources") or [],
        "error": body.get("error") or (answer if answer.startswith("Error details:") else None),
    }


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def save_results(name, payload):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{name}-{stamp}.json"
    out.write_text(json.dumps(payload, indent=2))
    return out


# ---------------------------------------------------------------- arXiv

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_arxiv_feed(xml_text):
    papers = []
    for entry in ET.fromstring(xml_text).findall("atom:entry", ATOM):
        def text(tag):
            el = entry.find(f"atom:{tag}", ATOM)
            return el.text.strip().replace("\n", " ") if el is not None and el.text else ""
        papers.append({
            "arxiv_id": text("id").split("/")[-1],
            "title": " ".join(text("title").split()),
            "abstract": " ".join(text("summary").split()),
        })
    return papers


def arxiv_search(query, max_results):
    """Same request the ingest Lambda makes (lambda_ingest/handler.py), so results match what was indexed."""
    params = {"search_query": f"all:{query.replace(' ', '+')}", "start": 0, "max_results": max_results}
    with urllib.request.urlopen(f"{ARXIV_API}?{urllib.parse.urlencode(params)}", timeout=60) as r:
        return _parse_arxiv_feed(r.read().decode())


def arxiv_by_ids(ids):
    papers = {}
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 50):
        if i:
            time.sleep(3)  # arXiv API asks for >= 3 s between requests
        params = {"id_list": ",".join(ids[i:i + 50]), "max_results": 50}
        with urllib.request.urlopen(f"{ARXIV_API}?{urllib.parse.urlencode(params)}", timeout=60) as r:
            for p in _parse_arxiv_feed(r.read().decode()):
                papers[p["arxiv_id"]] = p
    return papers
