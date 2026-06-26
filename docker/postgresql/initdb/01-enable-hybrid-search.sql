\connect deepclaw

-- 为默认业务库启用向量检索扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 为默认业务库启用 BM25 检索扩展
CREATE EXTENSION IF NOT EXISTS pg_search;
