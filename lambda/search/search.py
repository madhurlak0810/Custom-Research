import os
import json
import boto3

DB_SECRET_ARN = os.environ['DB_SECRET_ARN']
DB_CLUSTER_ARN = os.environ['DB_CLUSTER_ARN']
DATABASE_NAME = os.environ['DATABASE_NAME']

rds_data = boto3.client("rds-data")
bedrock = boto3.client("bedrock-runtime")


def get_embedding(text):
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text})
    )

    result = json.loads(response['body'].read())
    return result["embedding"]


def handler(event, context):
    body = json.loads(event.get("body", "{}"))
    query_text = body.get("query", "")

    if not query_text:
        return {"statusCode": 400, "body": "Missing 'query'."}

    embedding = get_embedding(query_text)

    # Vector similarity search
    sql = """
        SELECT papers.title, papers.abstract, papers.url
        FROM embeddings
        JOIN papers ON embeddings.paper_id = papers.paper_id
        ORDER BY embeddings.embedding <-> :embedding::vector
        LIMIT 5;
    """

    result = rds_data.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DATABASE_NAME,
        sql=sql,
        parameters=[
            {
                "name": "embedding",
                "value": {
                    "stringValue": "[" + ",".join(map(str, embedding)) + "]"
                }
            }
        ]
    )

    response = []
    for record in result["records"]:
        title = record[0]["stringValue"]
        abstract = record[1]["stringValue"]
        url = record[2]["stringValue"]
        response.append({"title": title, "abstract": abstract, "url": url})

    return {
        "statusCode": 200,
        "body": json.dumps(response)
    }