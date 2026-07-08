"""Study Assistant ORM 模型定义"""
import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, Text, DateTime, Date, Integer, JSON, ForeignKey, Boolean
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import relationship
from backend.core.database import Base


def _uuid_str():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    name = Column(String(200), nullable=False)
    source_type = Column(String(20), nullable=False, default="file")  # file/git/concept
    source_path = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    learnability_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    learning_content = relationship("LearningContent", back_populates="project", uselist=False, cascade="all, delete-orphan")
    qa_records = relationship("QARecord", back_populates="project", cascade="all, delete-orphan")
    feynman_sessions = relationship("FeynmanSession", back_populates="project", cascade="all, delete-orphan")
    learning_logs = relationship("LearningLog", back_populates="project", cascade="all, delete-orphan")


class LearningContent(Base):
    __tablename__ = "learning_contents"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False)
    title = Column(String(500), nullable=True)
    framework_json = Column(JSON, nullable=True)
    explanation_md = Column(Text, nullable=True)
    sq3r_json = Column(JSON, nullable=True)
    raw_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="learning_content")


class QARecord(Base):
    __tablename__ = "qa_records"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source_type = Column(String(20), default="summary")  # summary/rag/web
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="qa_records")


class FeynmanSession(Base):
    __tablename__ = "feynman_sessions"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    session_data = Column(JSON, default=list)
    weak_points = Column(JSON, nullable=True)
    status = Column(String(20), default="active")  # active/completed
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="feynman_sessions")


class LearningLog(Base):
    __tablename__ = "learning_logs"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    log_date = Column(Date, default=date.today)
    knowledge_summary = Column(Text, nullable=True)
    weak_points = Column(Text, nullable=True)
    session_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="learning_logs")


class DocumentChunk(Base):
    """父块持久化存储 — ParentDocumentRetriever 的文档层"""
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    parent_text = Column(Text, nullable=False)
    child_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    last_accessed_at = Column(DateTime, default=_now)


class ProjectBackgroundKnowledge(Base):
    """项目背景知识 — 对话历史摘要持久化"""
    __tablename__ = "project_background_knowledge"

    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                        primary_key=True, nullable=False)
    user_intents = Column(Text, default="")
    assistant_actions = Column(Text, default="")
    key_facts = Column(Text, default="")
    message_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
