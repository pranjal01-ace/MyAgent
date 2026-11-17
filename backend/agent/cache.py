import ast
import operator
import re
import logging
import concurrent.futures
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict
from datetime import datetime

logger = logging.getLogger("ace.cache")
_cache_bg_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache_bg")

# Safe math operators for AST evaluation
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    """Safely evaluates an AST node containing only numbers and basic operators."""
    if isinstance(node, ast.Constant):  # Python 3.8+ (numbers, strings)
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Non-numeric constant")
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type}")
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type}")
    else:
        raise ValueError(f"Unsupported AST node: {type(node)}")


def evaluate_constant_math(text: str) -> Optional[str]:
    """Detects constant arithmetic expressions (e.g., '2+2', 'what is 25 * 4?', 'calculate (10+5)/3')
    and solves them deterministically without needing LLM reasoning.
    """
    raw = text.strip()
    lowered = raw.lower()

    # Extract potential math expression from phrases like "what is 2+2", "calculate 5*8", "2 + 2"
    cleaned = re.sub(r"^(?:what\s+is|calculate|evaluate|solve|compute|\?|=|how\s+much\s+is)\s+", "", lowered)
    cleaned = cleaned.rstrip("?").strip()

    # Replace symbols like ^ with **
    cleaned = cleaned.replace("^", "**").replace("x", "*").replace("×", "*").replace("÷", "/")

    # Check if cleaned string only contains numbers, operators, parentheses, and spaces
    if not re.fullmatch(r"[\d\s\+\-\*\/\%\(\)\.]+", cleaned):
        return None

    # Must contain at least one operator and one digit to avoid matching single numbers or empty
    if not re.search(r"[\+\-\*\/\%]", cleaned) or not re.search(r"\d", cleaned):
        return None

    try:
        parsed = ast.parse(cleaned, mode="eval")
        result = _eval_node(parsed.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"{raw.rstrip('?').strip()} = **{result}**"
    except Exception:
        return None


def normalize_prompt(text: str) -> str:
    """Normalize query to lowercase, collapsed spaces, and stripped trailing punctuation."""
    lowered = text.lower().strip()
    cleaned = re.sub(r"[?!.,;]+$", "", lowered)
    return " ".join(cleaned.split())


def compute_jaccard_similarity(text1: str, text2: str) -> float:
    """Fast lexical similarity between two normalized prompt strings."""
    tokens1 = set(text1.lower().split())
    tokens2 = set(text2.lower().split())
    if not tokens1 or not tokens2:
        return 0.0
    return len(tokens1 & tokens2) / len(tokens1 | tokens2)


def get_prompt_embedding(text: str) -> Optional[list]:
    """Generates embedding vector for semantic caching using the local embedding generator."""
    try:
        from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator
        return OllamaEmbeddingGenerator().get_embedding_sync(text)
    except Exception as e:
        logger.debug(f"Could not generate embedding for cache: {e}")
        return None


class PersistentResponseCache:
    """Multi-Tier Context-Aware Response Cache:
    1. Fast in-memory LRU exact composite match (~0.05ms)
    2. Persistent PostgreSQL database exact context match (~2ms)
    3. Lexical Jaccard similarity match with entity validation (~0.1ms)
    4. PostgreSQL vector cosine similarity match with entity compatibility validation (~15ms)
    5. Conversation history fallback with context safety
    """

    def __init__(self, max_memory_size: int = 500, semantic_threshold: float = 0.92):
        self.max_memory_size = max_memory_size
        self.semantic_threshold = semantic_threshold
        self._memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    @staticmethod
    def build_cache_key(prompt: str, context_key: Optional[str] = None, entity: Optional[str] = None) -> str:
        """Constructs a deterministic unique composite cache key combining prompt and context."""
        norm_prompt = normalize_prompt(prompt)
        ctx = (entity or context_key or "").lower().strip()
        if ctx and ctx != "general":
            clean_ctx = re.sub(r"[^\w\s-]", "", ctx).replace(" ", "_")
            return f"{norm_prompt}::{clean_ctx}"
        return norm_prompt

    def _validate_candidate(
        self,
        candidate: Dict[str, Any],
        required_context: Optional[str] = None,
        required_entity: Optional[str] = None,
        required_topic: Optional[str] = None
    ) -> bool:
        """
        Validates if a cache candidate matches the active conversation context.
        Rejects candidates with conflicting entities, stale/invalidated status, or mismatched context.
        """
        # 1. Status check
        status = str(candidate.get("status", "ACTIVE")).upper()
        if status in {"STALE", "INVALIDATED"}:
            return False

        cand_entity = (candidate.get("entity") or "").lower().strip()
        cand_ctx = (candidate.get("context_key") or "").lower().strip()

        # 2. Entity conflict check
        if required_entity:
            req_e = required_entity.lower().strip()
            if cand_entity:
                # If both have non-empty entities that distinctly disagree (e.g. apple_inc vs fruit)
                if cand_entity != req_e and cand_entity not in req_e and req_e not in cand_entity:
                    logger.info(f"Cache candidate rejected due to entity mismatch: '{cand_entity}' != '{req_e}'")
                    return False
            else:
                # Candidate has no entity tag (legacy or uncontextualized entry).
                # Check whether candidate's response mentions required entity
                cand_resp = (candidate.get("response") or "").lower()
                if req_e not in cand_resp:
                    logger.info(f"Uncontextualized cache candidate rejected because required entity '{req_e}' is not in response")
                    return False

        # 3. Context key conflict check
        if required_context and cand_ctx and cand_ctx != "general":
            req_c = required_context.lower().strip()
            if cand_ctx != req_c and cand_ctx not in req_c and req_c not in cand_ctx:
                logger.info(f"Cache candidate rejected due to context mismatch: '{cand_ctx}' != '{req_c}'")
                return False

        return True

    def get(
        self,
        prompt: str,
        context_key: Optional[str] = None,
        entity: Optional[str] = None,
        topic: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve contextually compatible cached response across all 5 tiers."""
        raw_key = normalize_prompt(prompt)
        if not raw_key:
            return None

        composite_key = self.build_cache_key(prompt, context_key, entity)

        # 1. Tier 1: In-memory exact composite match (or raw_key only if unconstrained)
        lookup_keys = [composite_key] if (entity or context_key) else [composite_key, raw_key]
        for lookup_key in lookup_keys:
            if lookup_key in self._memory_cache:
                candidate = self._memory_cache[lookup_key]
                if self._validate_candidate(candidate, context_key, entity, topic):
                    self._memory_cache.move_to_end(lookup_key)
                    logger.info(f"Tier 1 (In-memory) cache hit for: '{prompt}' [key={lookup_key}]")
                    return candidate

        # 2. Tier 2: Database exact match
        try:
            from backend.memory.database import SessionLocal, QueryCacheModel, engine
            db = SessionLocal()
            try:
                # Try exact composite key first
                record = (
                    db.query(QueryCacheModel)
                    .filter(QueryCacheModel.cache_key == composite_key, QueryCacheModel.status == "ACTIVE")
                    .first()
                )
                # Fallback to normalized prompt only if no specific entity was required
                if not record and composite_key != raw_key and not entity:
                    record = (
                        db.query(QueryCacheModel)
                        .filter(QueryCacheModel.prompt_normalized == raw_key, QueryCacheModel.status == "ACTIVE")
                        .first()
                    )

                if record:
                    candidate_dict = {
                        "response": record.response,
                        "tool_executed": record.tool_executed,
                        "cached": True,
                        "source": "exact_cache",
                        "status": record.status,
                        "context_key": getattr(record, "context_key", "general"),
                        "entity": getattr(record, "entity", None),
                        "topic": getattr(record, "topic", None),
                    }

                    lowered_record_resp = (record.response or "").lower().strip()
                    if "error communicating with ollama" in lowered_record_resp or lowered_record_resp.startswith("[error") or lowered_record_resp.startswith("[ollama error"):
                        db.delete(record)
                        db.commit()
                    elif self._validate_candidate(candidate_dict, context_key, entity, topic):
                        record.hit_count = (record.hit_count or 1) + 1
                        db.commit()
                        self._memory_cache[composite_key] = candidate_dict
                        logger.info(f"Tier 2 (PostgreSQL exact) cache hit for: '{prompt}' [entity={getattr(record, 'entity', None)}]")
                        return candidate_dict

                # 3. Tier 3: Fast lexical/Jaccard similarity on in-memory keys
                for cached_key, cached_val in self._memory_cache.items():
                    sim = compute_jaccard_similarity(raw_key, cached_key.split("::")[0])
                    if sim >= 0.85:
                        if self._validate_candidate(cached_val, context_key, entity, topic):
                            logger.info(f"Tier 3 (Lexical Jaccard {sim:.2f}) cache hit: '{prompt}' -> '{cached_key}'")
                            return {
                                "response": cached_val["response"],
                                "tool_executed": cached_val.get("tool_executed"),
                                "cached": True,
                                "source": "lexical_cache",
                                "entity": cached_val.get("entity"),
                            }

                # 4. Tier 4: PostgreSQL vector cosine similarity with context validation
                if "postgresql" in str(engine.url):
                    query_vec = get_prompt_embedding(prompt)
                    if query_vec:
                        from sqlalchemy import text
                        sql = text("""
                            SELECT prompt_normalized, cache_key, response, tool_executed, entity, context_key, status,
                                   cosine_similarity(embedding, :vec) AS sim
                            FROM query_cache
                            WHERE embedding IS NOT NULL AND status = 'ACTIVE'
                            ORDER BY sim DESC
                            LIMIT 3;
                        """)
                        rows = db.execute(sql, {"vec": query_vec}).fetchall()
                        for row in rows:
                            if row and row.sim is not None and row.sim >= self.semantic_threshold:
                                row_candidate = {
                                    "response": row.response,
                                    "tool_executed": row.tool_executed,
                                    "entity": getattr(row, "entity", None),
                                    "context_key": getattr(row, "context_key", "general"),
                                    "status": getattr(row, "status", "ACTIVE"),
                                }
                                lowered_row_resp = (row.response or "").lower().strip()
                                if not ("error communicating with ollama" in lowered_row_resp or lowered_row_resp.startswith("[error") or lowered_row_resp.startswith("[ollama error")):
                                    if self._validate_candidate(row_candidate, context_key, entity, topic):
                                        logger.info(
                                            f"Tier 4 (Semantic Vector {row.sim:.3f} >= {self.semantic_threshold}) "
                                            f"cache hit for '{prompt}' -> matched '{row.prompt_normalized}'"
                                        )
                                        entry = {
                                            "response": row.response,
                                            "tool_executed": row.tool_executed,
                                            "cached": True,
                                            "source": "semantic_vector_cache",
                                            "similarity": float(row.sim),
                                            "entity": getattr(row, "entity", None),
                                        }
                                        self._memory_cache[composite_key] = entry
                                        return entry
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Error querying persistent cache: {e}")

        # 5. Tier 5: Check historical conversations table
        try:
            from backend.memory.database import SessionLocal, ConversationModel
            db = SessionLocal()
            try:
                user_records = (
                    db.query(ConversationModel)
                    .filter(ConversationModel.role == "user", ConversationModel.is_active == True)
                    .order_by(ConversationModel.id.desc())
                    .limit(300)
                    .all()
                )
                for u_rec in user_records:
                    if normalize_prompt(u_rec.content) == raw_key:
                        # Look up immediate next turn in conversation session
                        next_rec = (
                            db.query(ConversationModel)
                            .filter(
                                ConversationModel.id > u_rec.id,
                                ConversationModel.session_id == u_rec.session_id,
                                ConversationModel.is_active == True
                            )
                            .order_by(ConversationModel.id.asc())
                            .first()
                        )
                        # Must be an assistant message immediately following this user message
                        if not next_rec or next_rec.role != "assistant":
                            continue

                        ans_rec = next_rec
                        if ans_rec and ans_rec.content:
                            lowered_ans = ans_rec.content.lower().strip()
                            if "error communicating with ollama" in lowered_ans or lowered_ans.startswith("[error") or lowered_ans.startswith("[ollama error"):
                                continue

                            # Verify compatibility if entity is an external contextual constraint (e.g. fruit for apple)
                            if entity and entity.lower() not in raw_key and entity.lower() not in lowered_ans:
                                continue

                            entry = {
                                "response": ans_rec.content,
                                "tool_executed": None,
                                "cached": True,
                                "source": "conversation_history",
                                "entity": entity
                            }
                            self.set(prompt, ans_rec.content, context_key=context_key, entity=entity, topic=topic)
                            logger.info(f"Tier 5 (Conversation history) cache hit for: '{prompt}'")
                            return entry
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Error querying conversation history: {e}")

        return None

    def set(
        self,
        prompt: str,
        response: str,
        tool_executed: Optional[str] = None,
        context_key: Optional[str] = None,
        entity: Optional[str] = None,
        topic: Optional[str] = None
    ):
        """Stores constant prompt-response pair into memory and database with vector embedding and context."""
        raw_key = normalize_prompt(prompt)
        if not raw_key or not response:
            return

        lowered_resp = response.lower().strip()
        if "error communicating with ollama" in lowered_resp or lowered_resp.startswith("[error") or lowered_resp.startswith("[ollama error"):
            logger.debug("Refusing to cache error response.")
            return

        composite_key = self.build_cache_key(prompt, context_key, entity)

        entry = {
            "response": response,
            "tool_executed": tool_executed,
            "cached": True,
            "source": "in_memory",
            "context_key": context_key or "general",
            "entity": entity,
            "topic": topic,
            "status": "ACTIVE",
        }

        # 1. Store in memory immediately for instant 0.01ms retrieval
        if len(self._memory_cache) >= self.max_memory_size:
            self._memory_cache.popitem(last=False)
        self._memory_cache[composite_key] = entry

        # 2. Persist to PostgreSQL in background without blocking response
        def _persist_task():
            try:
                from backend.memory.database import SessionLocal, QueryCacheModel
                db = SessionLocal()
                try:
                    embedding = get_prompt_embedding(prompt)
                    existing = (
                        db.query(QueryCacheModel)
                        .filter(QueryCacheModel.cache_key == composite_key)
                        .first()
                    )
                    if not existing:
                        existing = (
                            db.query(QueryCacheModel)
                            .filter(QueryCacheModel.prompt_normalized == raw_key, QueryCacheModel.context_key == (context_key or "general"))
                            .first()
                        )

                    if existing:
                        existing.response = response
                        existing.tool_executed = tool_executed
                        existing.cache_key = composite_key
                        existing.context_key = context_key or "general"
                        existing.topic = topic
                        existing.entity = entity
                        existing.status = "ACTIVE"
                        existing.is_active = True
                        if embedding:
                            existing.embedding = embedding
                    else:
                        new_rec = QueryCacheModel(
                            prompt_normalized=raw_key,
                            cache_key=composite_key,
                            context_key=context_key or "general",
                            topic=topic,
                            entity=entity,
                            status="ACTIVE",
                            response=response,
                            tool_executed=tool_executed,
                            embedding=embedding
                        )
                        db.add(new_rec)
                    db.commit()
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"Error persisting to query_cache: {e}")

        try:
            _cache_bg_pool.submit(_persist_task)
        except Exception as e:
            logger.warning(f"Cache persistence background task submission failed (best-effort): {e}")

    def invalidate_context(
        self,
        topic: Optional[str] = None,
        entity: Optional[str] = None,
        conflicting_context: Optional[str] = None
    ) -> int:
        """
        Multi-Tier Cache Invalidation Engine:
        Cascades invalidation across L1 (Memory), L2 (PostgreSQL), L3 (Lexical), and L4 (Semantic)
        marking conflicting entries STALE and evicting them from memory.
        """
        invalidated_count = 0
        norm_topic = (topic or "").lower().strip()
        norm_entity = (entity or "").lower().strip()
        norm_conflict = (conflicting_context or "").lower().strip()

        logger.info(f"CACHE_INVALIDATION triggered: topic='{norm_topic}', entity='{norm_entity}', conflict='{norm_conflict}'")

        # 1. Invalidate in-memory L1 cache
        keys_to_evict = []
        for k, v in list(self._memory_cache.items()):
            cand_ent = (v.get("entity") or "").lower().strip()
            cand_topic = (v.get("topic") or "").lower().strip()
            cand_resp = (v.get("response") or "").lower().strip()

            should_evict = False
            if norm_conflict and (norm_conflict in cand_ent or norm_conflict in cand_resp or norm_conflict in k):
                should_evict = True
            elif norm_topic and norm_entity and (norm_topic in k or norm_topic in cand_topic):
                # If topic matches but it was referencing the old interpretation
                if cand_ent and cand_ent != norm_entity:
                    should_evict = True

            if should_evict:
                keys_to_evict.append(k)

        for k in keys_to_evict:
            del self._memory_cache[k]
            invalidated_count += 1
            logger.debug(f"L1 Memory cache evicted key: {k}")

        # 2. Invalidate persistent L2 PostgreSQL query_cache table
        try:
            from backend.memory.database import SessionLocal, QueryCacheModel
            db = SessionLocal()
            try:
                query = db.query(QueryCacheModel).filter(QueryCacheModel.status == "ACTIVE")
                records = query.all()
                for rec in records:
                    rec_ent = (rec.entity or "").lower().strip()
                    rec_topic = (rec.topic or "").lower().strip()
                    rec_prompt = (rec.prompt_normalized or "").lower().strip()
                    rec_resp = (rec.response or "").lower().strip()

                    match_conflict = False
                    if norm_conflict and (norm_conflict in rec_ent or norm_conflict in rec_resp or norm_conflict in rec_prompt):
                        match_conflict = True
                    elif norm_topic and norm_entity and (norm_topic in rec_prompt or norm_topic in rec_topic):
                        if rec_ent and rec_ent != norm_entity:
                            match_conflict = True

                    if match_conflict:
                        rec.status = "STALE"
                        rec.is_active = False
                        invalidated_count += 1
                db.commit()
                logger.info(f"L2 PostgreSQL cache marked {invalidated_count} rows as STALE")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Error executing database cache invalidation: {e}")

        return invalidated_count

    def clear(self):
        """Clears both in-memory cache and persistent query_cache table."""
        self._memory_cache.clear()
        try:
            from backend.memory.database import SessionLocal, QueryCacheModel
            db = SessionLocal()
            try:
                db.query(QueryCacheModel).delete()
                db.commit()
            finally:
                db.close()
        except Exception:
            pass


# Global singleton cache instance
response_cache = PersistentResponseCache()

