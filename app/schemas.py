"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------- 全局常量 ----------
# 固定 4 个明确错因（评审砍掉"其他"：模糊归因低价值，且绑架看板口径）
ERROR_CAUSES: list[str] = [
    "知识点不知道",
    "知识点不熟悉",
    "没思路",
    "粗心大意",
]


# ---------- 分类 ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    color: str = "#141414"


class CategoryOut(BaseModel):
    id: int
    name: str
    color: str
    count: int = 0
    sort_order: int = 0


# ---------- 错题 ----------
class MistakeIn(BaseModel):
    category_id: Optional[int] = None
    subject: str = ""
    knowledge_point: str = ""
    error_cause: str = ""
    source: str = ""
    content: str = Field(min_length=1)
    answer: str = ""


class MistakeUpdate(BaseModel):
    category_id: Optional[int] = None
    subject: Optional[str] = None
    knowledge_point: Optional[str] = None
    error_cause: Optional[str] = None
    source: Optional[str] = None
    content: Optional[str] = None
    answer: Optional[str] = None
    mastered: Optional[bool] = None
    reviewed: Optional[bool] = None


class MistakeOut(BaseModel):
    id: int
    category_id: Optional[int]
    subject: str
    knowledge_point: str
    error_cause: str
    source: str
    content: str
    answer: str
    ai_analysis: str
    review_count: int
    mastered: bool
    reviewed: bool
    created_at: str


class PageOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MistakeOut]


# ---------- AI 解析 / 录入 ----------
class OcrResult(BaseModel):
    text: str
    split: list[dict]
    engine_status: str = ""


class AnnotateResult(BaseModel):
    subject: str
    knowledge_point: str
    error_cause: str
    source: str


# ---------- 对话 ----------
class ChatSessionOut(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str


class MessageIn(BaseModel):
    session_id: Optional[int] = None
    content: str = Field(min_length=1)


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: str


class ConvertIn(BaseModel):
    message_id: int
    original_content: str = ""  # 用户原题（前端从 user 消息取，单题时拼到 content 前面）


# ---------- 复习 ----------
class ReviewPlanOut(BaseModel):
    id: int
    mistake_id: int
    due_date: str
    plan_type: str
    status: str
    content: str = ""
    subject: str = ""


class ReviewStartIn(BaseModel):
    subject: Optional[str] = None
    category_id: Optional[int] = None
    count: int = Field(default=3, ge=1, le=10, description="变体题数量，上限 10（防止 LLM 调用被打爆）")


class VariantQuestion(BaseModel):
    id: int
    original: dict
    variant: str


class AnswerIn(BaseModel):
    mistake_id: int
    question: str
    user_answer: str
    reference: str = ""


class GradeOut(BaseModel):
    score: int
    passed: bool
    comment: str
    quality: int


# ---------- 看板 ----------
class KpiOut(BaseModel):
    total: int
    mastered: int
    pending: int
    mastery_rate: int


class TrendPoint(BaseModel):
    label: str
    value: int


class ItemValue(BaseModel):
    label: str
    value: int
    color: str = "#141414"


class PlanItem(BaseModel):
    date: str
    subject: str
    knowledge_point: str
    pending: int


# ---------- 导出 ----------
class ExportIn(BaseModel):
    category_id: Optional[int] = None
    subject: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class ExportOut(BaseModel):
    filename: str
    path: str


# ---------- 帮助 ----------
class FaqOut(BaseModel):
    q: str
    a: str
