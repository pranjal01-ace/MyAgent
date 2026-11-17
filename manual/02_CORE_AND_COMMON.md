# ⚙️ Core & Common Foundation Manual

This document details the configuration management, database connectivity, pooling, schema migration, base audit models, and global exception handling under `backend/core/` and `backend/common/`.

---

## 1. System Configuration: `backend/core/config.py`

**File Location:** [`backend/core/config.py`](file:///D:/Ace_Ai/backend/core/config.py)

### Class: `Settings(BaseSettings)`
Centralized configuration class reading from `.env` with strong type validation via Pydantic:

| Setting Field | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `API_HOST` | `str` | `"0.0.0.0"` | Host IP interface for FastAPI server |
| `API_PORT` | `int` | `8000` | Port for FastAPI server |
| `DATABASE_URL` | `str` | `"postgresql://postgres:postgres@localhost:5432/ace_db"` | Primary PostgreSQL database URL (falls back to SQLite if unreachable) |
| `OLLAMA_URL` | `str` | `"http://localhost:11434"` | Ollama LLM HTTP server endpoint |
| `OLLAMA_MODEL` | `str` | `"mistral"` | Active local Ollama LLM model name |
| `TTS_ENGINE` | `str` | `"edge"` | Active speech synthesis backend (`"edge"` or `"sapi5"`) |
| `TTS_VOICE` | `str` | `"en-US-ChristopherNeural"` | Microsoft Edge-TTS natural voice name |
| `VAD_MIN_SILENCE_DURATION` | `float` | `0.4` | Minimum silence duration (seconds) before triggering end-of-speech |
| `WORKSPACE_ROOT` | `Path` | Directory root | Confined filesystem workspace for safe tool execution |

**Singleton Export:**
- `settings = Settings()`: Global configuration object imported across the backend.
- `BASE_DIR`: Absolute `Path` to the root `Ace_Ai` directory.

---

## 2. Database Engine & Lifecycle: `backend/core/database.py`

**File Location:** [`backend/core/database.py`](file:///D:/Ace_Ai/backend/core/database.py)

### Functions Reference

#### `create_db_engine() -> Engine`
* **Purpose:** Initializes the primary SQLAlchemy database engine with connection pooling and automated failover.
* **Connection Pooling Configuration:**
  - `pool_pre_ping=True`: Tests connection health before execution, preventing stale socket errors.
  - `pool_size=15`: Number of persistent database connections maintained in the pool.
  - `max_overflow=25`: Extra connections allowed under peak concurrent load.
  - `pool_recycle=1800`: Recycles connections after 30 minutes to avoid server-side timeouts.
* **Auto-Creation:** If the target PostgreSQL database does not exist, connects to default `postgres` catalog with `AUTOCOMMIT` and executes `CREATE DATABASE <name>`.
* **Fallback:** If PostgreSQL is unreachable, falls back to local SQLite at `data/agent.db`.

#### `get_db() -> Generator[Session, None, None]`
* **Purpose:** FastAPI dependency providing a thread-local `SessionLocal` instance per HTTP request.
* **Guarantees:** Closes database session in a `finally` block to prevent connection leaks.

#### `init_db() -> None`
* **Purpose:** Creates all database tables registered on `Base.metadata`.
* **Automated Non-Destructive Migrations:** Executes `ALTER TABLE ... ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP` and `is_active BOOLEAN` on PostgreSQL tables.
* **Vector Extensions:** Executes `CREATE EXTENSION IF NOT EXISTS vector;` and registers PL/pgSQL math functions:
  - `cosine_similarity(a float8[], b float8[]) -> float8`
  - `vector_dot_product(a float8[], b float8[]) -> float8`

---

## 3. Base Audit Model: `backend/common/models.py`

**File Location:** [`backend/common/models.py`](file:///D:/Ace_Ai/backend/common/models.py)

### Class: `BaseAuditModel(Base)`
Abstract base model inherited by all persistent database entities:

```python
class BaseAuditModel(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
```

| Field Name | Type | Properties | Purpose |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Indexed | Unique entity record identifier |
| `created_at` | `DateTime` | Default `utcnow`, Non-null | Creation timestamp in UTC |
| `updated_at` | `DateTime` | Auto-update on save | Timestamp of last modification |
| `is_active` | `Boolean` | Default `True`, Non-null | Soft-deletion flag preserving historical integrity |

---

## 4. Common Schemas: `backend/common/schemas.py`

**File Location:** [`backend/common/schemas.py`](file:///D:/Ace_Ai/backend/common/schemas.py)

* **`BaseAuditSchema(BaseModel)`**: Serializes audit metadata (`id`, `created_at`, `updated_at`, `is_active`) into JSON responses with Pydantic V2 `from_attributes = True`.
* **`GenericResponse(BaseModel)`**: Standardized envelope for operational status messages (`success: bool`, `message: str`, `data: Optional[Dict]`).

---

## 5. Domain Exceptions: `backend/common/exceptions.py` & `exception_handlers.py`

**File Locations:**
- [`backend/common/exceptions.py`](file:///D:/Ace_Ai/backend/common/exceptions.py)
- [`backend/common/exception_handlers.py`](file:///D:/Ace_Ai/backend/common/exception_handlers.py)

### Exception Hierarchy

```mermaid
graph TD
    Exception --> AppException
    AppException --> EntityNotFoundError
    AppException --> SecurityValidationError
    AppException --> ToolExecutionError
```

| Exception Class | Default HTTP Status | Description |
| :--- | :--- | :--- |
| `AppException` | `400 Bad Request` | Base application exception carrying `message`, `status_code`, and `details` dictionary |
| `EntityNotFoundError` | `404 Not Found` | Raised when an entity ID or memory key is missing |
| `SecurityValidationError` | `403 Forbidden` | Raised when path traversal or shell command injection is detected |
| `ToolExecutionError` | `500 Server Error` | Raised when desktop tool execution encounters an operating system error |

### Global Exception Handlers
- **`app_exception_handler`**: Catches any `AppException` and formats a standardized JSON response `{ "error": exc.message, "status_code": exc.status_code, "details": exc.details }`.
- **`generic_exception_handler`**: Catches unhandled Python exceptions, logs tracebacks to disk, and returns a sanitized HTTP 500 error preventing credential or stack trace leakage to clients.
