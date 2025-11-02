# Research Scrapper with Ollama

## 🚀 Quick Start

The scrapper is now working with Ollama and **REAL arXiv API**! Here are the key files:

- `scrapper_sqlite.py` - Real arXiv scrapper with SQLite (✅ **WORKING!**)
- `run_scrapper.py` - Easy-to-use runner with configurable parameters
- `search.py` - Search script to query your research database
- `.env` - Configuration file for default settings

## 📋 Current Status

✅ **Working**: Ollama embedding generation (768-dimension vectors)  
✅ **Working**: Real arXiv API using urllib (HTTP redirect issues fixed!)  
✅ **Working**: SQLite database storage with semantic search  
✅ **Working**: Semantic search functionality  

## 🔧 How to Use

### Quick Start - Scrape Real Papers:
```bash
# Scrape 10 real papers about machine learning
python3 run_scrapper.py --query "machine learning" --max-results 10

# Search your database
python3 search.py --query "neural networks" --top-k 5
```

### Change Parameters:

```bash
# Different topics
python3 run_scrapper.py --query "quantum computing" --max-results 15
python3 run_scrapper.py --query "computer vision" --max-results 8

# Smaller batch sizes for stability
python3 run_scrapper.py --embed-batch 1 --max-results 5

# Use different database
python3 run_scrapper.py --db-path "ai_papers.db" --query "artificial intelligence"

# Search with abstracts
python3 search.py --query "deep learning" --show-abstract --top-k 3
```  

## 🔧 How to Change Parameters

### Method 1: Using the Runner Script (Easiest)

```bash
# Change Ollama model
python3 run_scrapper.py --ollama-model "different-model" --query "AI research"

# Change batch size (smaller = more stable, slower)
python3 run_scrapper.py --embed-batch 1 --query "quantum computing"

# Use different database
python3 run_scrapper.py --db-path "my_research.db" --query "robotics"

# Search existing database only
python3 run_scrapper.py --search-only --query "machine learning"
```

### Method 2: Edit .env File

Modify `/root/src/Custom-Research/.env`:
```bash
# Ollama settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text  # Change this to use different models

# Database settings  
DB_PATH=papers.db

# Default parameters
DEFAULT_MAX_RESULTS=50              # Change default number of papers
DEFAULT_EMBED_BATCH_SIZE=16         # Change default batch size
DEFAULT_QUERY="machine learning"    # Change default search query
```

### Method 3: Direct Script Usage

```bash
# Real arXiv scrapping
python3 scrapper_sqlite.py --query "deep learning" --max-results 20 --embed-batch 3

# Search your database
python3 search.py --query "reinforcement learning" --top-k 5
```

## 🔍 Searching Your Database

After scraping papers, use the search script to find relevant papers:

```bash
# Basic search
python3 search.py --query "transformer architecture"

# Show more results
python3 search.py --query "quantum algorithms" --top-k 10

# Show abstracts
python3 search.py --query "machine learning" --show-abstract

# Search specific database
python3 search.py --query "neural networks" --db-path "my_research.db"
```

## 🎯 Common Parameter Changes

### 1. Change Search Query
```bash
python3 run_scrapper.py --query "reinforcement learning"
python3 run_scrapper.py --query "computer vision"
python3 run_scrapper.py --query "natural language processing"
```

### 2. Change Number of Papers
```bash
python3 run_scrapper.py --max-results 10    # More papers
python3 run_scrapper.py --max-results 3     # Fewer papers for testing
```

### 3. Change Embedding Batch Size
```bash
python3 run_scrapper.py --embed-batch 1     # Slower but more stable
python3 run_scrapper.py --embed-batch 5     # Faster but may stress Ollama
```

### 4. Change Ollama Model
```bash
# First, make sure the model is available in Ollama
ollama list

# Then use it
python3 run_scrapper.py --ollama-model "your-model-name"
```

### 5. Change Database Location
```bash
python3 run_scrapper.py --db-path "/path/to/your/database.db"
```

## 🔍 Available Models in Your Ollama

Current available model:
- `nomic-embed-text` ✅ (768 dimensions)

To add more embedding models:
```bash
ollama pull mxbai-embed-large    # Example: different embedding model
ollama pull all-minilm           # Example: another option
```

## 📊 Example Outputs

### Successful Scraping Example:
```
🔧 Configuration:
   Query: 'quantum computing'
   Max results: 5
   Embed batch: 2
   Database: papers.db
   Ollama URL: http://localhost:11434
   Ollama model: nomic-embed-text

🚀 Running arXiv scrapper...
Fetching 5 papers for query: 'quantum computing'
Request URL: http://export.arxiv.org/api/query?search_query=all:quantum+computing&start=0&max_results=5
Found 5 papers
  - Paper 1: The Rise of Quantum Internet Computing...
  - Paper 2: Unconventional Quantum Computing Devices...
✓ Successfully fetched 5 papers
Generating embeddings...
Embedding: 100%|████████| 3/3 [00:00<00:00, 3.70it/s]
✅ Scrapper completed successfully!
```

### Successful Search Example:
```
🔍 Searching for: 'neural networks'
📄 Database: papers.db

Generating embedding for: 'neural networks'
Searching through 13 papers...
📊 Found 3 results:

1. Lecture Notes: Optimization for Machine Learning (similarity: 0.710)
   arXiv ID: 1909.03550v1
   Authors: Elad Hazan
   PDF: http://arxiv.org/pdf/1909.03550v1
```

## 🛠️ Troubleshooting

### If Ollama is not responding:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if needed
ollama serve
```

### If embeddings are too slow:
- Reduce `--embed-batch` to 1 or 2
- Reduce `--max-results` for testing

## 🎉 What's New - arXiv API Fixed!

✅ **Fixed HTTP 301 redirect issues** by using urllib instead of arxiv library  
✅ **Real paper scraping now works** - no more demo-only mode  
✅ **Robust XML parsing** handles arXiv API responses properly  
✅ **Search functionality** to query your research database  
✅ **Full semantic search** with cosine similarity scoring  
✅ **Simplified codebase** with only essential files

The scrapper now successfully fetches real papers from arXiv and stores them with embeddings! 🎉
