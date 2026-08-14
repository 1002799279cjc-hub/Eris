"""错题与分类路由：CRUD、OCR 录入、AI 标注、AI 解析。"""
import asyncio
import sqlite3
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import database as db
from ..schemas import (AnnotateResult, CategoryIn, CategoryOut, MistakeIn,
                       MistakeOut, MistakeUpdate, OcrResult, PageOut)
from ..services import ocr_service, vector_store
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api", tags=["mistakes"])


async def _index_async(mistake_id: int, content: str, metadata: dict) -> None:
    """向量索引异步化：3 秒超时，失败仅跳过（不阻塞录入主流程）。"""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(vector_store.index_mistake, mistake_id, content, metadata),
            timeout=3,
        )
    except Exception:
        pass


# ---------- 分类 ----------
@router.get("/categories")
def list_categories():
    """返回所有分类 + 每分类错题数 + 全量错题数 + 未分类数（保证侧栏口径一致）。"""
    conn = db.get_conn()
    try:
        cats = conn.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM mistakes m WHERE m.category_id=c.id) AS count
               FROM categories c ORDER BY c.sort_order, c.id"""
        ).fetchall()
        all_count = conn.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0]
        unclassified_count = conn.execute(
            "SELECT COUNT(*) FROM mistakes WHERE category_id IS NULL"
        ).fetchone()[0]
        return {"items": db.rows_to_dicts(cats), "all_count": all_count, "unclassified_count": unclassified_count}
    finally:
        conn.close()


@router.post("/categories", response_model=CategoryOut)
def create_category(data: CategoryIn):
    conn = db.get_conn()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO categories(name,color,sort_order,created_at) VALUES(?,?,?,?)",
                (data.name, data.color, 99, db.now_str()),
            )
        except Exception:
            raise HTTPException(400, "分类已存在")
        conn.commit()
        row = conn.execute("SELECT * FROM categories WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row) | {"count": 0}
    finally:
        conn.close()


@router.delete("/categories/{category_id}")
def delete_category(category_id: int):
    """删除分类：将该分类下的错题 category_id 置为 NULL（错题本身保留）。"""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            raise HTTPException(404, "分类不存在")
        conn.execute("UPDATE mistakes SET category_id=NULL WHERE category_id=?", (category_id,))
        conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
        conn.commit()
        return {"ok": True, "moved_mistakes": True}
    finally:
        conn.close()


# ---------- 错题 CRUD ----------
@router.get("/mistakes", response_model=PageOut)
def list_mistakes(
    category_id: int | None = None,
    status: str | None = None,      # all | pending | mastered | unreviewed | week
    subject: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    conn = db.get_conn()
    try:
        where, params = ["1=1"], []
        if category_id is not None:
            # 特殊值 -1 表示"未分类"（侧栏用）
            if category_id == -1:
                where.append("category_id IS NULL")
            else:
                where.append("category_id=?"); params.append(category_id)
        if subject:
            where.append("subject=?"); params.append(subject)
        if status == "mastered":
            where.append("mastered=1")
        elif status == "pending":
            where.append("mastered=0")
        elif status == "unreviewed":
            where.append("reviewed=0")
        elif status == "week":
            where.append("created_at>=date('now','-7 days')")
        if keyword:
            where.append("(content LIKE ? OR knowledge_point LIKE ? OR subject LIKE ?)")
            params += [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]
        w = " AND ".join(where)
        total = conn.execute(f"SELECT COUNT(*) FROM mistakes WHERE {w}", params).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM mistakes WHERE {w} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        return {"total": total, "page": page, "page_size": page_size,
                "items": db.rows_to_dicts(rows)}
    finally:
        conn.close()


def _check_category(conn, category_id) -> None:
    """N5 修复：分类存在性校验（非法 category_id → 400，避免外键约束 500）。"""
    if category_id is not None:
        row = conn.execute("SELECT id FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            raise HTTPException(400, "分类不存在")


@router.post("/mistakes", response_model=MistakeOut)
async def create_mistake(data: MistakeIn):
    conn = db.get_conn()
    try:
        note = data.model_dump()
        # N5 修复：先校验分类存在
        _check_category(conn, note.get("category_id"))
        # AI 自动标注（未指定时）
        if not note.get("subject"):
            ann = await ai_service.annotate_mistake(data.content)
            note.update({k: (v or "") for k, v in ann.items()})
            # 新增：自动按学科名匹配已有分类（同名则归入，否则保持 NULL=未分类）
            subj = note.get("subject", "").strip()
            if subj and not note.get("category_id"):
                row = conn.execute(
                    "SELECT id FROM categories WHERE name=? LIMIT 1", (subj,)
                ).fetchone()
                if row:
                    note["category_id"] = row["id"]
        cur = conn.execute(
            """INSERT INTO mistakes(category_id,subject,knowledge_point,error_cause,source,
               content,answer,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (note.get("category_id"), note.get("subject", ""), note.get("knowledge_point", ""),
             note.get("error_cause", ""), note.get("source", ""), data.content, data.answer,
             db.now_str(), db.now_str()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM mistakes WHERE id=?", (cur.lastrowid,)).fetchone()
        await _index_async(cur.lastrowid, data.content, dict(row))
        return dict(row)
    except sqlite3.IntegrityError:
        # 兜底：外键约束冲突 → 400 而非 500
        raise HTTPException(400, "分类不存在")
    finally:
        conn.close()


@router.get("/mistakes/{mistake_id}", response_model=MistakeOut)
def get_mistake(mistake_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
        if not row:
            raise HTTPException(404, "错题不存在")
        return dict(row)
    finally:
        conn.close()


@router.patch("/mistakes/{mistake_id}", response_model=MistakeOut)
def update_mistake(mistake_id: int, data: MistakeUpdate):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
        if not row:
            raise HTTPException(404, "错题不存在")
        patch = data.model_dump()
        # N7 修复：不用 exclude_none（会把 category_id=null 过滤掉导致"移出分类"失效）；
        # 改为手动跳过空值；category_id=None 显式执行 `category_id=NULL`
        if patch.get("category_id") is not None:
            _check_category(conn, patch["category_id"])
        fields, params = [], []
        for key, val in patch.items():
            if val is None:
                if key == "category_id":
                    fields.append("category_id=NULL")
                continue
            fields.append(f"{key}=?")
            params.append(int(val) if isinstance(val, bool) else val)
        fields.append("updated_at=?"); params.append(db.now_str())
        params.append(mistake_id)
        conn.execute(f"UPDATE mistakes SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        row = conn.execute("SELECT * FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/mistakes/{mistake_id}")
def delete_mistake(mistake_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
        if not row:
            raise HTTPException(404, "错题不存在")
        conn.execute("DELETE FROM mistakes WHERE id=?", (mistake_id,))
        conn.execute("DELETE FROM review_plans WHERE mistake_id=?", (mistake_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------- OCR 录入 ----------
@router.post("/mistakes/ocr", response_model=OcrResult)
async def ocr_upload(file: UploadFile = File(...)):
    # 文件类型白名单 + 大小上限（防止坏图/非图片长时间挂起）
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
    if (file.content_type or "") not in allowed:
        raise HTTPException(400, f"仅支持图片文件（jpeg/png/webp/gif/bmp），收到：{file.content_type}")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "图片过大，请上传 10MB 以内的图片")
    path = ocr_service.save_upload(content, file.filename or "upload.png")
    try:
        # 识别整体加 60s 超时（坏图/网络异常快速失败，避免前端长时间转圈）
        text, status = await asyncio.wait_for(
            ocr_service.recognize_image(path), timeout=60
        )
    except asyncio.TimeoutError:
        return {"text": "【识别超时】图片处理超过 60 秒，请换一张清晰的图片重试。",
                "split": [], "engine_status": "OCR 识别超时（60s）"}
    # 模拟 AI 多题拆分（演示：按空行/序号切分）
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    split = []
    for p in parts[:5]:
        ann = await ai_service.annotate_mistake(p)
        split.append({"content": p, **ann})
    if not split:
        ann = await ai_service.annotate_mistake(text)
        split.append({"content": text, **ann})
    return {"text": text, "split": split, "engine_status": status}


# ---------- AI 解析 ----------
@router.post("/mistakes/{mistake_id}/analysis")
async def ai_analysis(mistake_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
        if not row:
            raise HTTPException(404, "错题不存在")
        m = dict(row)
        analysis = await ai_service.ai_analysis(m["content"], m["answer"])
        conn.execute("UPDATE mistakes SET ai_analysis=?, updated_at=? WHERE id=?",
                     (analysis, db.now_str(), mistake_id))
        conn.commit()
        return {"analysis": analysis}
    finally:
        conn.close()
