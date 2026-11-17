"""
Database Core Module.

Initializes SQLAlchemy database engine with connection pooling, session lifecycle management,
PostgreSQL vector math extensions, and automated non-destructive schema migrations.
"""

import logging
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from backend.core.config import settings, BASE_DIR
from backend.common.models import Base

logger = logging.getLogger("ace.core.database")

# Custom PostgreSQL vector functions for cosine similarity and dot product
COSINE_SIMILARITY_SQL = """
CREATE OR REPLACE FUNCTION cosine_similarity(a float8[], b float8[]) RETURNS float8 AS $$
DECLARE
    dot float8 := 0;
    norm_a float8 := 0;
    norm_b float8 := 0;
    i int;
    len int;
BEGIN
    len := array_length(a, 1);
    IF len IS NULL OR len != array_length(b, 1) THEN
        RETURN 0;
    END IF;
    FOR i IN 1..len LOOP
        dot := dot + a[i] * b[i];
        norm_a := norm_a + a[i] * a[i];
        norm_b := norm_b + b[i] * b[i];
    END LOOP;
    IF norm_a = 0 OR norm_b = 0 THEN
        RETURN 0;
    END IF;
    RETURN dot / (sqrt(norm_a) * sqrt(norm_b));
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""

VECTOR_DOT_PRODUCT_SQL = """
CREATE OR REPLACE FUNCTION vector_dot_product(a float8[], b float8[]) RETURNS float8 AS $$
DECLARE
    dot float8 := 0;
    i int;
    len int;
BEGIN
    len := array_length(a, 1);
    IF len IS NULL OR len != array_length(b, 1) THEN
        RETURN 0;
    END IF;
    FOR i IN 1..len LOOP
        dot := dot + a[i] * b[i];
    END LOOP;
    RETURN dot;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""


def create_db_engine():
    """
    Initializes primary database engine (PostgreSQL with fallback to SQLite).

    Configures connection pooling with pool_pre_ping=True, pool_size=15,
    and max_overflow=25 for non-blocking concurrent performance.
    """
    db_url = settings.DATABASE_URL

    # Resolve relative SQLite path if configured
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        rel_part = db_url.replace("sqlite:///", "")
        if rel_part.startswith("./") or not Path(rel_part).is_absolute():
            abs_db_path = (BASE_DIR / rel_part).resolve()
            abs_db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{abs_db_path.as_posix()}"

    try:
        connect_args = {}
        engine_kwargs = {"pool_pre_ping": True}

        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        else:
            engine_kwargs.update({
                "pool_size": 15,
                "max_overflow": 25,
                "pool_timeout": 15,
                "pool_recycle": 1800,
            })

        eng = create_engine(db_url, connect_args=connect_args, **engine_kwargs)
        with eng.connect() as conn:
            pass
        logger.info(f"Database engine initialized successfully with {db_url}")
        return eng

    except Exception as e:
        # Auto-create PostgreSQL database if missing on the server
        if "postgresql" in db_url and "does not exist" in str(e).lower():
            try:
                import re
                m = re.match(r"(postgresql(?:\+psycopg2)?://[^/]+)/([^?]+)", db_url)
                if m:
                    base_pg_url, db_name = m.group(1), m.group(2)
                    logger.info(f"Database '{db_name}' missing on PostgreSQL server. Auto-creating...")
                    pg_admin_engine = create_engine(
                        f"{base_pg_url}/postgres",
                        isolation_level="AUTOCOMMIT"
                    )
                    with pg_admin_engine.connect() as conn:
                        conn.execute(text(f"CREATE DATABASE {db_name}"))
                    logger.info(f"Successfully auto-created PostgreSQL database '{db_name}'!")
                    eng = create_engine(db_url)
                    with eng.connect() as conn:
                        pass
                    return eng
            except Exception as create_err:
                logger.warning(f"Could not auto-create PostgreSQL database: {create_err}")

        logger.warning(f"Failed to connect to primary database ({db_url}): {e}")
        fallback_path = (BASE_DIR / "data" / "agent.db").resolve()
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_url = f"sqlite:///{fallback_path.as_posix()}"
        logger.info(f"Falling back to local SQLite database: {fallback_url}")
        return create_engine(fallback_url, connect_args={"check_same_thread": False})


# Global application engine and session factory
engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a thread-local database session per HTTP request.

    Guarantees session cleanup upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initializes all database tables, vector extensions, and audit columns.

    Executes non-destructive schema migrations (ADD COLUMN IF NOT EXISTS)
    to safely align existing PostgreSQL tables with BaseAuditModel columns.
    """
    # Import domain models so Base.metadata is fully populated
    from backend.conversations.models import ConversationModel, ConversationStateModel
    from backend.memories.models import MemoryModel
    from backend.cache.models import QueryCacheModel

    # Create missing tables
    Base.metadata.create_all(bind=engine)

    # Ensure audit columns exist on existing PostgreSQL tables
    if "postgresql" in engine.url.drivername:
        audit_migrations = [
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS cache_key VARCHAR(255);",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS context_key VARCHAR(100) DEFAULT 'general';",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS topic VARCHAR(100);",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS entity VARCHAR(100);",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'ACTIVE';",
            "ALTER TABLE query_cache ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;",
            "ALTER TABLE knowledge_vectors ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            "ALTER TABLE knowledge_vectors ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
        ]
        with engine.connect() as conn:
            for stmt in audit_migrations:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                except Exception as mig_err:
                    conn.rollback()
                    logger.debug(f"Audit migration skipped: {mig_err}")

            # Drop legacy strict single-column unique constraint on prompt_normalized if present
            try:
                conn.execute(text("ALTER TABLE query_cache DROP CONSTRAINT IF EXISTS query_cache_prompt_normalized_key;"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_query_cache_cache_key ON query_cache (cache_key);"))
                conn.commit()
            except Exception as uc_err:
                conn.rollback()
                logger.debug(f"Cache key index migration skipped: {uc_err}")

    # Initialize PostgreSQL vector functions and HNSW index if on PostgreSQL
    if "postgresql" in engine.url.drivername:
        try:
            with engine.connect() as conn:
                # Install vector extension if pgvector is available
                try:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                    conn.commit()
                except Exception as ext_err:
                    conn.rollback()
                    logger.debug(f"pgvector extension not installed in Postgres: {ext_err}")

                conn.execute(text(COSINE_SIMILARITY_SQL))
                conn.execute(text(VECTOR_DOT_PRODUCT_SQL))
                conn.commit()
                logger.info("PostgreSQL vector math functions registered successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize PostgreSQL vector functions: {e}")
