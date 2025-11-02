# Research Scrapper with Ollama

## Overview

A research paper scrapper that fetches papers from arXiv, generates embeddings using Ollama, and provides semantic search functionality.

**Key Features:**
- Real arXiv API integration with SQLite storage
- Ollama embedding generation (768-dimension vectors)
- Semantic search with cosine similarity
- Easy-to-use command line interface

**Files:**
- `run_scrapper.py` - Main runner script
- `scrapper_sqlite.py` - Direct scrapper script
- `search.py` - Search existing database
- `.env` - Configuration file

## Quick Start

```bash
# Scrape papers
python3 run_scrapper.py --query "machine learning" --max-results 10

# Search database
python3 search.py --query "neural networks" --top-k 5
```

## Usage

### Scraping Papers
```bash
# Basic usage
python3 run_scrapper.py --query "quantum computing" --max-results 15

# Adjust batch size for stability
python3 run_scrapper.py --embed-batch 1 --max-results 5

# Use different database
python3 run_scrapper.py --db-path "ai_papers.db" --query "artificial intelligence"

# Direct script usage
python3 scrapper_sqlite.py --query "deep learning" --max-results 20
```

### Searching
```bash
# Basic search
python3 search.py --query "transformer architecture"

# Show abstracts and more results
python3 search.py --query "machine learning" --show-abstract --top-k 10

# Search specific database
python3 search.py --query "neural networks" --db-path "my_research.db"

# Search existing database only (no scraping)
python3 run_scrapper.py --search-only --query "machine learning"
```

## Configuration

### Environment Variables (.env file)
```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
DB_PATH=papers.db
```

### Common Options
- `--query` - Search query for papers
- `--max-results` - Number of papers to fetch
- `--embed-batch` - Batch size for embeddings (1-2 for stability)
- `--db-path` - Database file location
- `--ollama-model` - Ollama model to use

## Troubleshooting

**Ollama not responding:**
```bash
curl http://localhost:11434/api/tags  # Check if running
ollama serve                          # Start if needed
```

**Slow embeddings:**
- Reduce `--embed-batch` to 1 or 2
- Reduce `--max-results` for testing
