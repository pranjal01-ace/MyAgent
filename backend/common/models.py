"""
Common Database Models & Audit Foundations
==========================================
Defines the root Declarative Base and BaseAuditModel which automatically equips
all downstream domain models (conversations, memories, cache, vectors) with:
  - id: Auto-increment primary key
  - created_at: UTC timestamp when the record was initially created
  - updated_at: UTC timestamp updated on each record modification
  - is_active: Boolean flag for soft-deletion and record lifecycle tracking
"""

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, Boolean
from sqlalchemy.orm import declarative_base

# Declarative metadata registry for SQLAlchemy
Base = declarative_base()


class BaseAuditModel(Base):
    """
    Abstract Base Model with automated audit trails.
    All persistent entities in the application should inherit from this class.
    """
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True, doc="Unique auto-incrementing primary key")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, doc="UTC creation timestamp")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, doc="UTC modification timestamp")
    is_active = Column(Boolean, default=True, nullable=False, doc="Active status flag for soft deletion")

    def to_dict(self) -> dict:
        """
        Serializes all table column attributes of this instance into a dictionary.

        Returns:
            dict: Mapping of column names to their current values.
        """
        return {
            c.name: getattr(self, c.name)
            for c in self.__table__.columns
        }
