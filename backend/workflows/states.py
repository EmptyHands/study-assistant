"""LangGraph 状态定义"""
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class LearningState(TypedDict):
    """主学习流程状态"""
    project_id: str
    source_type: str          # file / git / concept
    source_path: str          # 文件路径、git URL 或概念文本
    raw_content: str          # 解析后的原始文本
    is_learnable: bool
    learnability_reason: str
    content_type: str
    title: str
    framework: dict           # 框架分析结果
    explanation: dict         # SQ3R 讲解
    error: str


class QAState(TypedDict):
    """问答流程状态"""
    project_id: str
    question: str
    summary: str
    raw_content: str
    answer: str
    source_type: str          # summary / rag / web


class FeynmanState(TypedDict):
    """费曼学习流程状态"""
    project_id: str
    session_id: str
    title: str
    framework: dict
    key_concepts: list
    history: Annotated[list, add_messages]
    current_question: str
    user_answer: str
    evaluation: dict
    status: str               # questioning / waiting / evaluating / completed
    round_count: int


class UpdateState(TypedDict):
    """内容更新流程状态"""
    project_id: str
    raw_content: str
    existing_content: dict
    needs_update: bool
    supplements: list
    updated_content: dict
