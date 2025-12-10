#!/usr/bin/env python3

import sys
import os

# Add Lambda layer path
sys.path.insert(0, '/opt/python')

print("Python path:", sys.path)
print("Current working directory:", os.getcwd())
print("Files in /opt/python:", os.listdir('/opt/python') if os.path.exists('/opt/python') else 'Not found')

try:
    import boto3
    print("✅ boto3 imported successfully")
except Exception as e:
    print(f"❌ boto3 import failed: {e}")

try:
    import psycopg2
    print("✅ psycopg2 imported successfully")
except Exception as e:
    print(f"❌ psycopg2 import failed: {e}")

try:
    from common.db_utils import get_connection
    print("✅ db_utils imported successfully")
except Exception as e:
    print(f"❌ db_utils import failed: {e}")

try:
    from common.bedrock_utils import generate_embeddings
    print("✅ bedrock_utils imported successfully") 
except Exception as e:
    print(f"❌ bedrock_utils import failed: {e}")

print("Environment variables:")
for key, value in os.environ.items():
    if 'DB_' in key or 'BEDROCK_' in key:
        print(f"  {key}: {value}")