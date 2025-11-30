-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Table storing metadata
CREATE TABLE IF NOT EXISTS papers (
    paper_id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT NOT NULL,
    published DATE,
    url TEXT
);

-- Embedding table (768-dim or whatever model you use)
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    paper_id INT REFERENCES papers(paper_id),
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for faster similarity search
CREATE INDEX IF NOT EXISTS embedding_idx
ON embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);