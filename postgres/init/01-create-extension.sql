-- Runs once, on first container start, via /docker-entrypoint-initdb.d/.
CREATE EXTENSION IF NOT EXISTS vector;

-- 1) DOCUMENTS — 1 hàng / file .md
CREATE TABLE IF NOT EXISTS rag_documents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_path  TEXT NOT NULL UNIQUE,   -- vd rag-ai-local/QandA/07042026_....md
  raw_content  TEXT,                    -- [Lab1] toàn văn file
  -- [Lab2] điền từ frontmatter + TL;DR:
  doc_type VARCHAR(30), title TEXT, doc_date DATE, area VARCHAR(100),
  status VARCHAR(40), tags TEXT[], description TEXT, summary TEXT,
  metadata JSONB, created_at TIMESTAMP DEFAULT NOW()
);

-- 2) CHUNKS — nhiều chunk fixed-token / document
CREATE TABLE IF NOT EXISTS rag_chunks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES rag_documents(id) ON DELETE CASCADE,
  chunk_index INT, content TEXT NOT NULL, token_count INT,  -- [Lab1]
  metadata JSONB,                    -- [Lab2]
  content_tsv tsvector,               -- [Lab3] full-text
  UNIQUE (document_id, chunk_index)
);

-- 3) EMBEDDINGS — 1 vector / chunk
CREATE TABLE IF NOT EXISTS rag_embeddings (
  id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id UUID REFERENCES rag_chunks(id) ON DELETE CASCADE,
  embedding vector(768) NOT NULL,  -- 768 = nomic-embed-text
  model VARCHAR(80), UNIQUE (chunk_id)
);
