# ⚡ Multi-Tier Cache & Vector RAG Manual

This document details the multi-tier query caching subsystem, semantic embedding matching, pgvector HNSW indexing, and vector store integration under `backend/cache/` and `backend/memory/vector_store.py`.

---

## 1. Multi-Tier Caching Architecture

To achieve near-zero latency (<5ms) for repeated or semantically equivalent questions, Ace AI implements a 3-tier caching hierarchy:

```mermaid
graph TD
    Prompt[User Input Prompt] --> T1{Tier 1: Exact Match}
    T1 -->|Hit (<1ms)| Return[Return Cached Response]
    T1 -->|Miss| T2{Tier 2: Normalized Match}
    T2 -->|Hit (<3ms)| Return
    T2 -->|Miss| T3{Tier 3: Semantic Cache}
    T3 -->|Embedding Cosine >= 0.90| Return
    T3 -->|Miss| LLM[Forward to Ollama LLM]
```

### The 3 Cache Tiers Explained

1. **Tier 1: Exact Match Cache**
   - Matches raw string identical queries directly against memory cache.
2. **Tier 2: Normalized Cache**
   - Normalizes input by lowercasing, stripping leading/trailing punctuation (`?`, `!`, `.`), and collapsing multiple spaces into a single space.
   - Example: `"Who are you?"` matches `"who are you"`.
3. **Tier 3: Semantic Embedding Cache**
   - Generates vector embedding of input prompt via Ollama embeddings API (`nomic-embed-text`).
   - Computes cosine similarity against previously stored prompt embeddings.
   - Triggers a hit if similarity exceeds threshold (default `0.90`).
   - Example: `"What is your identity?"` hits cached answer for `"Who are you?"`.

---

## 2. Query Cache Model: `backend/cache/models.py`

**File Location:** [`backend/cache/models.py`](file:///D:/Ace_Ai/backend/cache/models.py)

### Class: `QueryCacheModel(BaseAuditModel)`
Stored in table `query_cache`:

```python
class QueryCacheModel(BaseAuditModel):
    __tablename__ = "query_cache"

    prompt_normalized = Column(String(512), unique=True, index=True, nullable=False)
    response = Column(Text, nullable=False)
    tool_executed = Column(String(255), nullable=True)
    embedding = Column(ARRAY(Float), nullable=True)
    hit_count = Column(Integer, default=1, nullable=False)
```

| Field Name | Type | Properties | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key | Cache record ID (inherited from `BaseAuditModel`) |
| `prompt_normalized` | `String(512)` | Unique, Indexed | Normalized prompt string |
| `response` | `Text` | Non-null | Pre-computed LLM answer |
| `tool_executed` | `String(255)` | Nullable | Name/parameters of tool if one was run |
| `embedding` | `ARRAY(Float)` | Nullable | Float array embedding for semantic similarity search |
| `hit_count` | `Integer` | Default `1` | Total number of times this cache entry served a query |
| `created_at` | `DateTime` | Auto-set | UTC timestamp of entry creation |
| `updated_at` | `DateTime` | Auto-update | UTC timestamp of last cache hit/update |
| `is_active` | `Boolean` | Default `True` | Active status flag |

---

## 3. Cache Repository: `backend/cache/repository.py`

**File Location:** [`backend/cache/repository.py`](file:///D:/Ace_Ai/backend/cache/repository.py)

### Class: `CacheRepository`
Data access layer for prompt caching:

* **`get_by_normalized_prompt(prompt_norm: str) -> Optional[QueryCacheModel]`**: Retrieves an active entry by exact normalized string match.
* **`save_cache_entry(prompt_norm: str, response: str, tool_executed: Optional[str], embedding: Optional[List[float]]) -> QueryCacheModel`**: Upserts entry, updates hit count, and commits to database.
* **`increment_hit_count(entry_id: int) -> None`**: Atomically increments `hit_count`.
* **`clear() -> None`**: Purges all entries from `query_cache`.

---

## 4. Vector Store & RAG: `backend/memory/vector_store.py`

**File Location:** [`backend/memory/vector_store.py`](file:///D:/Ace_Ai/backend/memory/vector_store.py)

### Class: `PostgresVectorStore`
Manages document embedding storage and nearest-neighbor vector retrieval for Retrieval-Augmented Generation (RAG):

#### Features
- **HNSW Indexing:** Utilizes pgvector Hierarchical Navigable Small World (HNSW) index for sub-millisecond approximate nearest neighbor searches.
- **Failover Recovery:** If PostgreSQL or pgvector is unavailable, seamlessly falls back to an in-memory cosine index or Qdrant without application crashing.

#### Method Reference
* **`add_documents(texts: List[str], metadatas: Optional[List[Dict]] = None) -> List[str]`**: Ingests batches of text chunks, generates vector embeddings, and stores them in `knowledge_vectors`.
* **`similarity_search(query: str, k: int = 4) -> List[Dict[str, Any]]`**: Embeds query, executes vector cosine distance search, and returns the top `k` most relevant context chunks.
* **`delete(doc_ids: List[str]) -> bool`**: Deletes vector chunks by identifier.
