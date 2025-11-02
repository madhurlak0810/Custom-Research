"""
Fetch N results from arXiv, embed title+abstract via Ollama, and push to SQLite.

Usage:
    python scrapper_sqlite.py --query "machine learning" --max-results 50

Note:
- Ensure Ollama is running (ollama serve) with an embedding model (e.g., nomic-embed-text)
"""
import os
import time
import json
import click
import requests
import sqlite3
import pickle
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DB_PATH = os.getenv("DB_PATH", "papers.db")


def embed_texts_ollama(texts, model=None, base_url=None):
    if model is None:
        model = OLLAMA_EMBED_MODEL
    if base_url is None:
        base_url = OLLAMA_BASE_URL
    
    vectors = []
    for text in texts:
        headers = {"Content-Type": "application/json"}
        body = {"model": model, "prompt": text}
        resp = requests.post(f"{base_url}/api/embeddings", headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "embedding" in data:
            vectors.append(data["embedding"])
        else:
            raise RuntimeError("Unexpected Ollama response: %s" % json.dumps(data)[:400])
    return vectors


def fetch_arxiv_papers(query, max_results=50):
    """
    Fetch papers from arXiv using direct urllib requests
    """
    import urllib.request
    import xml.etree.ElementTree as ET
    from urllib.parse import quote_plus
    
    results = []
    
    try:
        print(f"Fetching {max_results} papers for query: '{query}'")
        
        # URL encode the query and build request URL
        encoded_query = quote_plus(query)
        url = f'http://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results={max_results}'
        
        print(f"Request URL: {url}")
        
        # Fetch data using urllib
        data = urllib.request.urlopen(url)
        response_text = data.read().decode('utf-8')
        
        # Parse XML response
        root = ET.fromstring(response_text)
        
        # Define namespaces for XML parsing
        namespaces = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        
        # Find all paper entries
        entries = root.findall('atom:entry', namespaces)
        print(f"Found {len(entries)} papers")
        
        for i, entry in enumerate(entries):
            try:
                # Extract arXiv ID
                id_elem = entry.find('atom:id', namespaces)
                arxiv_id = id_elem.text.split('/')[-1] if id_elem is not None else f"unknown_{i}"
                
                # Extract title
                title_elem = entry.find('atom:title', namespaces)
                title = title_elem.text.strip() if title_elem is not None else "No title"
                
                # Extract abstract/summary
                summary_elem = entry.find('atom:summary', namespaces)
                abstract = summary_elem.text.replace('\n', ' ').strip() if summary_elem is not None else "No abstract"
                
                # Extract authors
                authors = []
                for author in entry.findall('atom:author', namespaces):
                    name_elem = author.find('atom:name', namespaces)
                    if name_elem is not None:
                        authors.append(name_elem.text)
                
                # Extract publication date
                published_elem = entry.find('atom:published', namespaces)
                published = published_elem.text if published_elem is not None else None
                
                # Extract PDF URL
                pdf_url = None
                for link in entry.findall('atom:link', namespaces):
                    if link.get('type') == 'application/pdf':
                        pdf_url = link.get('href')
                        break
                
                # If no PDF link found, construct it from arXiv ID
                if pdf_url is None:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                
                paper = {
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "pdf_url": pdf_url,
                    "published": published,
                }
                
                results.append(paper)
                print(f"  - Paper {len(results)}: {title[:60]}...")
                
            except Exception as e:
                print(f"Error parsing paper {i}: {e}")
                continue
        
        print(f"✓ Successfully fetched {len(results)} papers")
        return results
        
    except Exception as e:
        print(f"❌ Error fetching papers: {e}")
        print("Try again later or use the demo mode:")
        print("  python3 run_scrapper.py --mode demo --query 'your query'")
        return []


def setup_db(db_path):
    """Create SQLite database and table for papers"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            arxiv_id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            authors TEXT,
            pdf_url TEXT,
            published TEXT,
            embedding BLOB
        )
    """)
    conn.commit()
    return conn


def insert_papers(conn, papers):
    """Insert papers into SQLite database"""
    cursor = conn.cursor()
    
    for paper in papers:
        # Serialize the embedding vector
        embedding_blob = pickle.dumps(paper['vector'])
        authors_str = json.dumps(paper['authors'])
        
        cursor.execute("""
            INSERT OR REPLACE INTO papers 
            (arxiv_id, title, abstract, authors, pdf_url, published, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            paper['arxiv_id'],
            paper['title'],
            paper['abstract'],
            authors_str,
            paper['pdf_url'],
            paper['published'],
            embedding_blob
        ))
    
    conn.commit()


@click.command()
@click.option("--query", "-q", default="machine learning", help="arXiv search query")
@click.option("--max-results", "-n", default=50, help="Max number of papers to fetch")
@click.option("--embed-batch", "-b", default=16, help="Embedding batch size")
@click.option("--db-path", default="papers.db", help="SQLite database path")
def main(query, max_results, embed_batch, db_path):
    print(f"Fetching papers for query: '{query}'")
    papers = fetch_arxiv_papers(query=query, max_results=max_results)
    if not papers:
        print("No papers found.")
        return

    print(f"Found {len(papers)} papers")
    texts = [f"{p['title']}\n\n{p['abstract']}" for p in papers]

    print("Generating embeddings...")
    all_vectors = []
    for i in tqdm(range(0, len(texts), embed_batch), desc="Embedding"):
        batch_texts = texts[i : i + embed_batch]
        vecs = embed_texts_ollama(batch_texts)
        all_vectors.extend(vecs)
        time.sleep(0.2)

    if len(all_vectors) != len(papers):
        raise RuntimeError("embeddings count mismatch")

    # prepare items
    items = []
    for p, v in zip(papers, all_vectors):
        items.append(
            {
                "arxiv_id": p["arxiv_id"],
                "title": p["title"],
                "abstract": p["abstract"],
                "authors": p["authors"],
                "pdf_url": p["pdf_url"],
                "published": p["published"],
                "vector": v,
            }
        )

    print("Setting up database...")
    conn = setup_db(db_path)
    
    print("Inserting papers into database...")
    insert_papers(conn, items)
    
    conn.close()
    print(f"Done! Inserted {len(items)} papers into {db_path}")


if __name__ == "__main__":
    main()