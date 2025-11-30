import os
import json
import boto3
import requests

# --------------------------
# ENVIRONMENT VARIABLES
# --------------------------
DB_SECRET_ARN = os.environ['DB_SECRET_ARN']
DB_CLUSTER_ARN = os.environ['DB_CLUSTER_ARN']
DATABASE_NAME = os.environ['DATABASE_NAME']

# RDS Data API client
rds_data = boto3.client("rds-data")

# Bedrock client
bedrock = boto3.client("bedrock-runtime")


# --------------------------
# Generate Embeddings using Bedrock Titan v2
# --------------------------
def get_embedding(text):
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text})
    )

    result = json.loads(response['body'].read())
    return result["embedding"]


# --------------------------
# Insert into Aurora
# --------------------------
def insert_into_db(title, authors, abstract, embedding, url):
    sql1 = """
        INSERT INTO papers (title, authors, abstract, url)
        VALUES(:title, :authors, :abstract, :url)
        RETURNING paper_id;
    """

    # Insert paper metadata
    result = rds_data.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DATABASE_NAME,
        sql=sql1,
        parameters=[
            {"name": "title", "value": {"stringValue": title}},
            {"name": "authors", "value": {"stringValue": authors}},
            {"name": "abstract", "value": {"stringValue": abstract}},
            {"name": "url", "value": {"stringValue": url}},
        ]
    )

    paper_id = result["records"][0][0]["longValue"]

    # Insert embedding
    sql2 = """
        INSERT INTO embeddings (paper_id, embedding)
        VALUES(:paper_id, :embedding::vector);
    """

    rds_data.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DATABASE_NAME,
        sql=sql2,
        parameters=[
            {"name": "paper_id", "value": {"longValue": paper_id}},
            {"name": "embedding", "value": {"stringValue": "[" + ",".join(map(str, embedding)) + "]"}},
        ]
    )


# --------------------------
# Handler
# --------------------------
def handler(event, context):
    # Example: fetch ML papers from arXiv
    url = "https://export.arxiv.org/api/query?search_query=cat:cs.LG&start=0&max_results=2"

    response = requests.get(url)
    data = response.text

    # Extremely simplified parse (for demo)
    entries = data.split("<entry>")[1:3]  # take first 2 papers

    for entry in entries:
        title = entry.split("<title>")[1].split("</title>")[0].strip()
        abstract = entry.split("<summary>")[1].split("</summary>")[0].strip()
        authors = "Unknown"
        link = "https://arxiv.org"

        # Generate embedding
        embedding = get_embedding(title + "\n" + abstract)

        # Insert into DB
        insert_into_db(title, authors, abstract, embedding, link)

    return {
        "statusCode": 200,
        "body": "Scraper executed successfully"
    }