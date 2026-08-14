"""复习路由：SM-2 复习计划、一键复习（变体题 + AI 批改）。"""
import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from .. import database as db
from ..schemas import AnswerIn, GradeOut, ReviewPlanOut, ReviewStartIn, VariantQuestion
from ..services import sm2
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/review", tags=["review"])

# 单题变体生成超时兜底（正常约 10-15s；超时跳过该题，不阻塞整轮）
_VARIANT_TIMEOUT = 60.0


def _compute_state(conn, mistake_id: int) -> sm2.SM2State:
    rows = conn.execute(
        "SELECT score FROM review_records WHERE mistake_id=? ORDER BY id DESC LIMIT 1",
        (mistake_id,),
    ).fetchall()
    state = sm2.initial_state()
    for r in rows:
        state = sm2.review(state, max(0, min(5, int(r["score"] // 20))))
    return state


@router.get("/plans", response_model=list[ReviewPlanOut])
def list_plans(days: int = 7):
    """返回近 days 天的复习计划（含错题摘要）。"""
    conn = db.get_conn()
    try:
        since = (date.today() + timedelta(days=1)).isoformat()
        until = (date.today() + timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT p.*, m.content, m.subject, m.knowledge_point
               FROM review_plans p JOIN mistakes m ON m.id=p.mistake_id
               WHERE p.due_date BETWEEN ? AND ? AND p.status='pending'
               ORDER BY p.due_date""",
            (since, until),
        ).fetchall()
        return db.rows_to_dicts(rows)
    finally:
        conn.close()


@router.get("/plans/generate")
def generate_plans():
    """按 SM-2 为待复习错题生成未来计划（幂等）。"""
    conn = db.get_conn()
    try:
        mistakes = conn.execute(
            "SELECT * FROM mistakes WHERE mastered=0 ORDER BY review_count ASC"
        ).fetchall()
        created = 0
        for m in mistakes:
            state = _compute_state(conn, m["id"])
            if state.due_days <= 0:
                continue
            due = (date.today() + timedelta(days=state.due_days)).isoformat()
            exist = conn.execute(
                "SELECT 1 FROM review_plans WHERE mistake_id=? AND due_date=?",
                (m["id"], due),
            ).fetchone()
            if not exist:
                conn.execute(
                    "INSERT INTO review_plans(mistake_id,due_date,plan_type,status,created_at) VALUES(?,?,?,?,?)",
                    (m["id"], due, sm2.plan_type_for(state.due_days), "pending", db.now_str()),
                )
                created += 1
        conn.commit()
        return {"created": created}
    finally:
        conn.close()


@router.post("/start", response_model=list[VariantQuestion])
async def start_review(data: ReviewStartIn):
    """选择学科/分类后，AI 生成变体题队列。
    找不到时不静默 fallback 到全学科（避免用户选了语文却出地理题），
    返回空列表让前端提示「该学科暂无待复习错题」。
    """
    conn = db.get_conn()
    try:
        where, params = ["mastered=0"], []
        if data.subject:
            where.append("subject=?"); params.append(data.subject)
        if data.category_id:
            where.append("category_id=?"); params.append(data.category_id)
        rows = conn.execute(
            f"SELECT * FROM mistakes WHERE {' AND '.join(where)} ORDER BY review_count ASC LIMIT ?",
            params + [data.count],
        ).fetchall()
        # N8 优化：变体题生成并发（asyncio.gather），N 道题耗时从串行 N×t 降到接近 t
        import asyncio as _asyncio

        async def _gen_one(m: dict) -> dict | None:
            try:
                variant = await _asyncio.wait_for(
                    ai_service.generate_variant(dict(m)), timeout=_VARIANT_TIMEOUT
                )
            except Exception:
                return None  # 单题生成失败/超时：跳过该题，不影响整轮
            return {"id": m["id"], "original": dict(m), "variant": variant}

        out = [r for r in await _asyncio.gather(*(_gen_one(m) for m in rows)) if r]
        return out
    finally:
        conn.close()


@router.post("/grade", response_model=GradeOut)
async def grade(data: AnswerIn):
    """逐题作答后 AI 批改，并回写 SM-2 状态与复习记录。"""
    result = await ai_service.grade_answer(data.question, data.user_answer, data.reference)
    quality = 5 if result["passed"] else 2
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM mistakes WHERE id=?", (data.mistake_id,)).fetchone()
        if not row:
            raise HTTPException(404, "错题不存在")
        m = dict(row)
        state = _compute_state(conn, data.mistake_id)
        state = sm2.review(state, quality)
        conn.execute(
            "INSERT INTO review_records(mistake_id,score,passed,created_at) VALUES(?,?,?,?)",
            (data.mistake_id, result["score"], int(result["passed"]), db.now_str()),
        )
        conn.execute(
            "UPDATE mistakes SET review_count=review_count+1, reviewed=1, "
            "mastered=?, updated_at=? WHERE id=?",
            (int(result["passed"]), db.now_str(), data.mistake_id),
        )
        # 生成下一次到期计划
        if not result["passed"]:
            due = (date.today() + timedelta(days=1)).isoformat()
            conn.execute(
                "INSERT INTO review_plans(mistake_id,due_date,plan_type,status,created_at) VALUES(?,?,?,?,?)",
                (data.mistake_id, due, "day", "pending", db.now_str()),
            )
        conn.commit()
        return result | {"quality": quality}
    finally:
        conn.close()
