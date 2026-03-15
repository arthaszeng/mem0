import datetime
import enum
import logging
import uuid

import sqlalchemy as sa
from app.database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    types,
)
from sqlalchemy.orm import Session, relationship


class UUIDString(types.TypeDecorator):
    """UUID stored as 32-char hex in SQLite, matching the original UUID type behavior.

    Accepts both UUID objects and string values (with or without dashes) on input,
    always stores as 32-char hex (no dashes) for backward compatibility with
    existing data written by SQLAlchemy's native UUID type.
    """

    impl = types.String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value.hex
        try:
            return uuid.UUID(str(value)).hex
        except (ValueError, AttributeError):
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value

logger = logging.getLogger(__name__)


def get_current_utc_time():
    """Get current UTC time"""
    return datetime.datetime.now(datetime.UTC)


class MemoryState(enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"
    deleted = "deleted"
    expired = "expired"


class ProjectRole(enum.Enum):
    owner = "owner"
    admin = "admin"
    read_write = "read_write"
    read_only = "read_only"


class Project(Base):
    __tablename__ = "projects"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    owner_id = Column(UUIDString, ForeignKey("users.id"), nullable=False, index=True)
    description = Column(String, nullable=True)
    is_default = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)
    updated_at = Column(DateTime, default=get_current_utc_time, onupdate=get_current_utc_time)

    owner = relationship("User", backref="owned_projects")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    project_id = Column(UUIDString, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(UUIDString, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(Enum(ProjectRole), nullable=False, default=ProjectRole.read_write)
    created_at = Column(DateTime, default=get_current_utc_time)

    project = relationship("Project", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_user"),
    )


class InviteStatus(enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class ProjectInvite(Base):
    __tablename__ = "project_invites"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    role = Column(Enum(ProjectRole), nullable=False, default=ProjectRole.read_write)
    status = Column(Enum(InviteStatus), nullable=False, default=InviteStatus.pending)
    created_by_id = Column(UUIDString, ForeignKey("users.id"), nullable=False, index=True)
    accepted_by_id = Column(UUIDString, ForeignKey("users.id"), nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)
    accepted_at = Column(DateTime, nullable=True)

    project = relationship("Project", backref="invites")
    created_by = relationship("User", foreign_keys=[created_by_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_id])

    __table_args__ = (
        Index("idx_invite_project_status", "project_id", "status"),
    )


class User(Base):
    __tablename__ = "users"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    user_id = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    metadata_ = Column('metadata', JSON, default=dict)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)
    updated_at = Column(DateTime,
                        default=get_current_utc_time,
                        onupdate=get_current_utc_time)

    apps = relationship("App", back_populates="owner")
    memories = relationship("Memory", back_populates="user")


class App(Base):
    __tablename__ = "apps"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    owner_id = Column(UUIDString, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(String)
    metadata_ = Column('metadata', JSON, default=dict)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)
    updated_at = Column(DateTime,
                        default=get_current_utc_time,
                        onupdate=get_current_utc_time)

    owner = relationship("User", back_populates="apps")
    memories = relationship("Memory", back_populates="app")

    __table_args__ = (
        sa.UniqueConstraint('owner_id', 'name', name='idx_app_owner_name'),
    )


class Config(Base):
    __tablename__ = "configs"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=get_current_utc_time)
    updated_at = Column(DateTime,
                        default=get_current_utc_time,
                        onupdate=get_current_utc_time)


class Memory(Base):
    __tablename__ = "memories"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    user_id = Column(UUIDString, ForeignKey("users.id"), nullable=False, index=True)
    app_id = Column(UUIDString, ForeignKey("apps.id"), nullable=False, index=True)
    project_id = Column(UUIDString, ForeignKey("projects.id"), nullable=True, index=True)
    content = Column(String, nullable=False)
    vector = Column(String)
    metadata_ = Column('metadata', JSON, default=dict)
    state = Column(Enum(MemoryState), default=MemoryState.active, index=True)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)
    updated_at = Column(DateTime,
                        default=get_current_utc_time,
                        onupdate=get_current_utc_time)
    archived_at = Column(DateTime, nullable=True, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    run_id = Column(String, nullable=True, index=True)

    user = relationship("User", back_populates="memories")
    app = relationship("App", back_populates="memories")
    project = relationship("Project", backref="memories")
    categories = relationship("Category", secondary="memory_categories", back_populates="memories")

    __table_args__ = (
        Index('idx_memory_user_state', 'user_id', 'state'),
        Index('idx_memory_app_state', 'app_id', 'state'),
        Index('idx_memory_user_app', 'user_id', 'app_id'),
        Index('idx_memory_project', 'project_id'),
        Index('idx_memory_expires', 'expires_at'),
        Index('idx_memory_run', 'run_id'),
    )


class Category(Base):
    __tablename__ = "categories"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC), index=True)
    updated_at = Column(DateTime,
                        default=get_current_utc_time,
                        onupdate=get_current_utc_time)

    memories = relationship("Memory", secondary="memory_categories", back_populates="categories")

memory_categories = Table(
    "memory_categories", Base.metadata,
    Column("memory_id", UUIDString, ForeignKey("memories.id"), primary_key=True, index=True),
    Column("category_id", UUIDString, ForeignKey("categories.id"), primary_key=True, index=True),
    Index('idx_memory_category', 'memory_id', 'category_id')
)


class AccessControl(Base):
    __tablename__ = "access_controls"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    subject_type = Column(String, nullable=False, index=True)
    subject_id = Column(UUIDString, nullable=True, index=True)
    object_type = Column(String, nullable=False, index=True)
    object_id = Column(UUIDString, nullable=True, index=True)
    effect = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)

    __table_args__ = (
        Index('idx_access_subject', 'subject_type', 'subject_id'),
        Index('idx_access_object', 'object_type', 'object_id'),
    )


class ArchivePolicy(Base):
    __tablename__ = "archive_policies"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    criteria_type = Column(String, nullable=False, index=True)
    criteria_id = Column(String, nullable=True, index=True)
    days_to_archive = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=get_current_utc_time, index=True)

    __table_args__ = (
        Index('idx_policy_criteria', 'criteria_type', 'criteria_id'),
    )


class MemoryStatusHistory(Base):
    __tablename__ = "memory_status_history"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    memory_id = Column(UUIDString, ForeignKey("memories.id"), nullable=False, index=True)
    changed_by = Column(UUIDString, ForeignKey("users.id"), nullable=False, index=True)
    old_state = Column(Enum(MemoryState), nullable=False, index=True)
    new_state = Column(Enum(MemoryState), nullable=False, index=True)
    changed_at = Column(DateTime, default=get_current_utc_time, index=True)

    __table_args__ = (
        Index('idx_history_memory_state', 'memory_id', 'new_state'),
        Index('idx_history_user_time', 'changed_by', 'changed_at'),
    )


class MemoryAccessLog(Base):
    __tablename__ = "memory_access_logs"
    id = Column(UUIDString, primary_key=True, default=lambda: uuid.uuid4())
    memory_id = Column(UUIDString, ForeignKey("memories.id"), nullable=False, index=True)
    app_id = Column(UUIDString, ForeignKey("apps.id"), nullable=False, index=True)
    accessed_at = Column(DateTime, default=get_current_utc_time, index=True)
    access_type = Column(String, nullable=False, index=True)
    metadata_ = Column('metadata', JSON, default=dict)

    __table_args__ = (
        Index('idx_access_memory_time', 'memory_id', 'accessed_at'),
        Index('idx_access_app_time', 'app_id', 'accessed_at'),
    )

def categorize_memory_background(memory_id: uuid.UUID, content: str) -> None:
    """Classify a memory (domain + categories + tags) in the background.

    Also performs a second-pass sensitive data check on the stored content.
    If the LLM fact extraction leaked a secret, we mask it here before
    it persists.
    """
    from app.database import SessionLocal
    from app.utils.categorization import classify_memory
    from app.utils.sensitive import has_sensitive_content, mask_sensitive

    db = SessionLocal()
    try:
        # Second-pass: mask any sensitive data that survived ingestion
        memory = db.query(Memory).filter(Memory.id == memory_id).first()
        if memory and has_sensitive_content(memory.content):
            original = memory.content
            memory.content = mask_sensitive(memory.content)
            logger.warning(
                "Sensitive data detected in memory %s during post-storage check; masked",
                memory_id,
            )

        domain, categories, tags = classify_memory(content)

        db.execute(
            memory_categories.delete().where(memory_categories.c.memory_id == memory_id)
        )

        for category_name in categories:
            category = db.query(Category).filter(Category.name == category_name).first()
            if not category:
                category = Category(
                    name=category_name,
                    description=f"Automatically created category for {category_name}"
                )
                db.add(category)
                db.flush()

            db.execute(
                memory_categories.insert().values(
                    memory_id=memory_id,
                    category_id=category.id
                )
            )

        if memory:
            meta = dict(memory.metadata_ or {})
            meta["domain"] = domain
            meta["tags"] = tags
            memory.metadata_ = meta
            sa.orm.attributes.flag_modified(memory, "metadata_")

        db.commit()
        logger.info(
            "Classified memory %s: domain=%s, categories=%s, tags=%s",
            memory_id, domain, categories, tags,
        )
    except Exception as e:
        db.rollback()
        logger.error("Background categorization failed for %s: %s", memory_id, e)
    finally:
        db.close()
