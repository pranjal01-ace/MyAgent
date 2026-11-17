# 🧠 Memories Domain Manual

This document details the long-term memory system, persistent user facts, preference storage, schema validation, and REST API endpoints under `backend/memories/`.

---

## 1. Memory Model: `backend/memories/models.py`

**File Location:** [`backend/memories/models.py`](file:///D:/Ace_Ai/backend/memories/models.py)

### Class: `MemoryModel(BaseAuditModel)`
Represents persistent facts, preferences, and details stored in the database table `memories`:

```python
class MemoryModel(BaseAuditModel):
    __tablename__ = "memories"

    key = Column(String(120), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(50), default="general", index=True, nullable=False)
```

| Field Name | Type | Properties | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key | Unique memory record ID |
| `key` | `String(120)` | Unique, Indexed | Unique identifier/title (e.g. `"user_name"`, `"favorite_food"`) |
| `value` | `Text` | Non-null | Memory text content or preference details |
| `category` | `String(50)` | Indexed | Classification tag (e.g. `"user_info"`, `"preferences"`, `"general"`) |
| `created_at` | `DateTime` | Auto-set | UTC timestamp when memory was created |
| `updated_at` | `DateTime` | Auto-update | UTC timestamp when memory value was last altered |
| `is_active` | `Boolean` | Default `True` | Soft deletion status flag |

---

## 2. Memory Schemas: `backend/memories/schemas.py`

**File Location:** [`backend/memories/schemas.py`](file:///D:/Ace_Ai/backend/memories/schemas.py)

* **`MemoryCreateSchema(BaseModel)`**: Validates payloads for creating or upserting memories (`key: str`, `value: str`, `category: Optional[str] = "general"`).
* **`MemoryUpdateSchema(BaseModel)`**: Validates optional modifications to existing memories.
* **`MemoryResponseSchema(BaseAuditSchema)`**: Serializes memory records including audit timestamps (`id`, `created_at`, `updated_at`, `is_active`, `key`, `value`, `category`).

---

## 3. Memory Repository: `backend/memories/repository.py`

**File Location:** [`backend/memories/repository.py`](file:///D:/Ace_Ai/backend/memories/repository.py)

### Class: `MemoryRepository`
Data access layer for memory persistence:

#### Method Reference

1. **`upsert_memory(key: str, value: str, category: str = "general") -> MemoryModel`**
   - **Parameters:** `key`, `value`, `category`.
   - **Behavior:** If a memory with `key` exists, updates `value`, `category`, and `is_active=True`, triggering automatic `updated_at` refresh. If missing, inserts a new record.
   - **Returns:** Persisted `MemoryModel` instance.

2. **`get_by_key(key: str) -> Optional[MemoryModel]`**
   - **Parameters:** `key`.
   - **Returns:** Active `MemoryModel` record, or `None` if not found.

3. **`get_all(category: Optional[str] = None) -> List[MemoryModel]`**
   - **Parameters:** Optional `category` filter.
   - **Returns:** List of all active memory records.

4. **`get_detailed() -> List[Dict[str, Any]]`**
   - **Returns:** List of serialized dictionaries with ISO-formatted timestamps (`id`, `key`, `value`, `category`, `created_at`, `updated_at`).

5. **`delete_by_key(key: str) -> bool`**
   - **Parameters:** `key`.
   - **Returns:** `True` if record was found and deleted, `False` otherwise.

6. **`count(category: Optional[str] = None) -> int`**
   - **Returns:** Total number of stored active memory entries.

---

## 4. Memory Service: `backend/memories/service.py`

**File Location:** [`backend/memories/service.py`](file:///D:/Ace_Ai/backend/memories/service.py)

### Class: `MemoryService`
Business layer coordinating memory validation and error handling:

* **`create_or_update_memory(key: str, value: str, category: str) -> MemoryModel`**: Strips whitespace, validates length, and delegates to repository.
* **`get_memory(key: str) -> MemoryModel`**: Raises `EntityNotFoundError` if the key does not exist.
* **`list_memories(category: Optional[str]) -> List[MemoryModel]`**: Retrieves memory list.
* **`list_memories_detailed() -> List[Dict[str, Any]]`**: Retrieves detailed list with ISO timestamps.
* **`remove_memory(key: str) -> bool`**: Deletes memory or raises `EntityNotFoundError`.

---

## 5. Endpoints Reference: `backend/memories/router.py`

**File Location:** [`backend/memories/router.py`](file:///D:/Ace_Ai/backend/memories/router.py)

| Method | Endpoint | Request Body | Response | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/memories` | Query `category` | `List[MemoryResponseSchema]` | List active memories |
| `GET` | `/api/memories/detailed` | None | `{"memories", "count"}` | List memories with ISO timestamps |
| `POST` | `/api/memories` | `MemoryCreateSchema` | `MemoryResponseSchema` | Create or update memory |
| `GET` | `/api/memories/{key}` | Path param | `MemoryResponseSchema` | Get memory by unique key |
| `DELETE` | `/api/memories/{key}` | Path param | `{"success", "message"}` | Delete memory by key |
| `POST` | `/api/memory` | `MemoryCreateSchema` | `{"status", "key", "value"}` | Legacy singular route for memory creation |
| `DELETE` | `/api/memory/{key}` | Path param | `{"status", "message"}` | Legacy singular route for memory deletion |
