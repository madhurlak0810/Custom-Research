# Chat UI

A simple web interface for the Serverless RAG Research Assistant.

## Features

- **Configuration**: Set your API endpoint URL
- **Paper Ingestion**: Add new papers by search query
- **Topic Management**: Filter conversations by research topic
- **Chat Interface**: Ask questions and get AI-powered responses
- **Source Citations**: View relevant papers with similarity scores

## Usage

1. **Open the interface**: Open `index.html` in your web browser
2. **Configure API**: Enter your deployed API endpoint URL
3. **Ingest papers**: Use the sidebar to fetch papers on specific topics
4. **Chat**: Ask questions about the research papers
5. **Filter by topic**: Select topics to focus your search

## Local Development

Start a simple HTTP server to avoid CORS issues:

```bash
# Python 3
python -m http.server 8000

# Python 2
python -m SimpleHTTPServer 8000

# Node.js (if you have http-server installed)
npx http-server -p 8000

# Or use VS Code Live Server extension
```

Then open `http://localhost:8000` in your browser.

## Configuration

The UI requires your deployed API Gateway endpoint URL. The format should be:
```
https://your-api-id.execute-api.region.amazonaws.com/prod
```

The configuration is saved in browser localStorage for convenience.

## API Integration

The interface calls these endpoints:
- `POST /ingest` - Ingest new papers
- `POST /chat` - Search and chat with papers

Both endpoints expect JSON payloads and return JSON responses as documented in the main README.