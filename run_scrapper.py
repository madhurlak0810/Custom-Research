#!/usr/bin/env python3
"""
Easy runner for the research scrapper with configurable parameters
"""
import click
import subprocess
import sys
import os

@click.command()
@click.option("--query", "-q", 
              default="machine learning", 
              help="Search query")
@click.option("--max-results", "-n", 
              default=5, 
              help="Maximum number of papers to fetch")
@click.option("--embed-batch", "-b", 
              default=2, 
              help="Embedding batch size (smaller = more stable)")
@click.option("--db-path", 
              default="papers.db", 
              help="Database file path")
@click.option("--search-only", 
              is_flag=True, 
              help="Only search existing database, don't scrape new papers")
@click.option("--ollama-model", 
              default="nomic-embed-text", 
              help="Ollama embedding model to use")
@click.option("--ollama-url", 
              default="http://localhost:11434", 
              help="Ollama base URL")
def main(query, max_results, embed_batch, db_path, search_only, ollama_model, ollama_url):
    """
    Research Scrapper Runner
    
    Examples:
        # Scrape real papers
        python run_scrapper.py --query "quantum computing" --max-results 10
        
        # Just search existing database
        python run_scrapper.py --search-only --query "neural networks"
        
        # Use different settings
        python run_scrapper.py --query "machine learning" --embed-batch 1 --max-results 5
    """
    
    # Set environment variables
    os.environ["OLLAMA_BASE_URL"] = ollama_url
    os.environ["OLLAMA_EMBED_MODEL"] = ollama_model
    
    print(f"🔧 Configuration:")
    print(f"   Query: '{query}'")
    print(f"   Max results: {max_results}")
    print(f"   Embed batch: {embed_batch}")
    print(f"   Database: {db_path}")
    print(f"   Ollama URL: {ollama_url}")
    print(f"   Ollama model: {ollama_model}")
    print()
    
    if search_only:
        # Just search existing database
        if not os.path.exists(db_path):
            print(f"❌ Database {db_path} not found! Run scrapping first.")
            return
        
        print("🔍 Searching existing database...")
        cmd = [
            sys.executable, "search.py",
            "--query", query,
            "--db-path", db_path,
            "--top-k", "5"
        ]
    else:
        # Run scrapping
        print("🚀 Running arXiv scrapper...")
        cmd = [
            sys.executable, "scrapper_sqlite.py",
            "--query", query,
            "--max-results", str(max_results),
            "--embed-batch", str(embed_batch),
            "--db-path", db_path
        ]
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n✅ Scrapper completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Scrapper failed with exit code {e.returncode}")
        print("Check the output above for error details.")
    except KeyboardInterrupt:
        print(f"\n⏹️  Scrapper interrupted by user")


if __name__ == "__main__":
    main()