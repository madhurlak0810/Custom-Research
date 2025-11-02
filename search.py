#!/usr/bin/env python3
"""
Search script for querying the research database
"""
import click
import sqlite3
import pickle
import json
import numpy as np
from typing import List, Tuple
import os
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

def embed_text_ollama(text: str) -> List[float]:
    """Generate embedding for a single text using Ollama"""
    headers = {"Content-Type": "application/json"}
    body = {"model": OLLAMA_EMBED_MODEL, "prompt": text}
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/embeddings", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "embedding" in data:
        return data["embedding"]
    else:
        raise RuntimeError("Unexpected Ollama response")

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def search_papers(db_path: str, query: str, top_k: int = 5) -> List[Tuple[dict, float]]:
    """Search for papers similar to the query"""
    
    # Generate embedding for the query
    print(f"Generating embedding for: '{query}'")
    query_embedding = embed_text_ollama(query)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all papers and their embeddings
    cursor.execute("SELECT arxiv_id, title, abstract, authors, pdf_url, published, embedding FROM papers")
    rows = cursor.fetchall()
    
    if not rows:
        print("No papers found in database!")
        return []
    
    print(f"Searching through {len(rows)} papers...")
    
    # Calculate similarities
    results = []
    for row in rows:
        arxiv_id, title, abstract, authors_str, pdf_url, published, embedding_blob = row
        
        # Deserialize embedding
        paper_embedding = pickle.loads(embedding_blob)
        
        # Calculate similarity
        similarity = cosine_similarity(query_embedding, paper_embedding)
        
        # Parse authors
        authors = json.loads(authors_str) if authors_str else []
        
        paper = {
            'arxiv_id': arxiv_id,
            'title': title,
            'abstract': abstract,
            'authors': authors,
            'pdf_url': pdf_url,
            'published': published
        }
        
        results.append((paper, similarity))
    
    # Sort by similarity and return top k
    results.sort(key=lambda x: x[1], reverse=True)
    conn.close()
    
    return results[:top_k]

@click.command()
@click.option("--query", "-q", required=True, help="Search query")
@click.option("--db-path", default="papers.db", help="Database file path")
@click.option("--top-k", default=5, help="Number of results to return")
@click.option("--show-abstract", is_flag=True, help="Show full abstracts")
def main(query, db_path, top_k, show_abstract):
    """Search research papers database"""
    
    if not os.path.exists(db_path):
        print(f"❌ Database {db_path} not found!")
        print("Run the scrapper first to populate the database:")
        print("  python3 run_scrapper.py --mode real --query 'your topic'")
        return
    
    print(f"🔍 Searching for: '{query}'")
    print(f"📄 Database: {db_path}")
    print()
    
    try:
        results = search_papers(db_path, query, top_k)
        
        if not results:
            print("No results found.")
            return
        
        print(f"📊 Found {len(results)} results:\n")
        
        for i, (paper, similarity) in enumerate(results, 1):
            print(f"{i}. {paper['title']} (similarity: {similarity:.3f})")
            print(f"   arXiv ID: {paper['arxiv_id']}")
            print(f"   Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
            print(f"   PDF: {paper['pdf_url']}")
            
            if show_abstract:
                abstract = paper['abstract']
                if len(abstract) > 200:
                    abstract = abstract[:200] + "..."
                print(f"   Abstract: {abstract}")
            
            print()
            
    except Exception as e:
        print(f"❌ Error searching: {e}")

if __name__ == "__main__":
    main()