"""AI 对话路由：会话管理、SSE 流式回答、拍照识题、一键加入错题本。"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import database as db
from ..schemas import (ChatSessionOut, ConvertIn, MessageIn, MessageOut,
                       MistakeOut)
from ..services import ocr_service, vector_store
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions():
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT 50"
        ).fetchall()
        return db.rows_to_dicts(rows)
    finally:
        conn.close()


@router.post("/sessions", response_model=ChatSessionOut)
def create_session(title: str = "新对话"):
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO chat_sessions(title,created_at,updated_at) VALUES(?,?,?)",
            (title, db.now_str(), db.now_str()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: int):
    conn = db.get_conn()
    try:
        sess = conn.execute("SELECT id FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        if not sess:
            raise HTTPException(404, "会话不存在")
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
        return db.rows_to_dicts(rows)
    finally:
        conn.close()


@router.post("/stream")
async def chat_stream(data: MessageIn):
    """SSE 流式对话。返回 text/event-stream。"""
    conn = db.get_conn()
    try:
        if data.session_id:
            cur = conn.execute("SELECT id FROM chat_sessions WHERE id=?", (data.session_id,)).fetchone()
            if not cur:
                raise HTTPException(404, "会话不存在")
            session_id = data.session_id
            conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (db.now_str(), session_id))
        else:
            cur = conn.execute(
                "INSERT INTO chat_sessions(title,created_at,updated_at) VALUES(?,?,?)",
                (data.content[:20] or "新对话", db.now_str(), db.now_str()),
            )
            session_id = cur.lastrowid
        # 持久化用户消息
        conn.execute(
            "INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
            (session_id, "user", data.content, db.now_str()),
        )
        conn.commit()
        # 历史上下文
        rows = conn.execute(
            "SELECT role,content FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT 8",
            (session_id,),
        ).fetchall()
        history = [dict(r) for r in reversed(rows)]
    finally:
        conn.close()

    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    async def gen():
        # 首帧：会话 ID（便于前端跳转）
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        buffer: list[str] = []
        async for delta in ai_service.stream_chat(messages):
            buffer.append(delta)
            yield f"data: {json.dumps({'type': 'delta', 'content': delta})}\n\n"
        full = "".join(buffer)
        conn2 = db.get_conn()
        try:
            conn2.execute(
                "INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                (session_id, "assistant", full, db.now_str()),
            )
            conn2.execute(
                "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=?",
                (data.content[:20] or "新对话", db.now_str(), session_id),
            )
            conn2.commit()
        finally:
            conn2.close()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    """删除对话会话（级联删除消息与转换记录）。"""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "会话不存在")
        conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM chat_conversions WHERE message_id IN (SELECT id FROM chat_messages WHERE session_id=?)", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        conn.commit()
        return {"ok": True, "deleted": session_id}
    finally:
        conn.close()


@router.post("/convert")
async def convert_to_mistake(data: ConvertIn):
    """把对话中的某条 AI 回答一键转成错题。
    - 若回复里包含 ### 问题 N 标记（多题），自动按题拆分为多条错题；
    - 否则作为单条错题录入；
    - 每条都调用 ai_service.annotate_mistake 自动标注学科/知识点/错因。
    """
    import re
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM chat_messages WHERE id=? AND role='assistant'",
            (data.message_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "消息不存在或不可转换")
        msg = dict(row)
        content = msg["content"]

        # 1) 检测多题标记：### 问题 N
        parts = re.split(r"###\s*问题\s*\d+\s*", content)
        # 剔除首尾空段
        parts = [p.strip() for p in parts if p.strip()]
        has_marker = len(parts) > 1

        # 2) 提取每段的【答案】【答案解析】【对应知识点】，同时保留原段作为 content
        def extract_three(block: str) -> dict[str, str]:
            out = {"answer": "", "analysis": "", "knowledge": "", "content": block.strip()}
            m = re.search(
                r"【答案】([\s\S]*?)【答案解析】([\s\S]*?)【对应知识点】([\s\S]*?)$",
                block.strip(),
            )
            if m:
                out["answer"] = m.group(1).strip()
                out["analysis"] = m.group(2).strip()
                out["knowledge"] = m.group(3).strip()
            return out

        questions = []
        if has_marker:
            for p in parts:
                questions.append(extract_three(p))
        else:
            single = extract_three(content)
            single["content"] = content
            questions.append(single)

        # 3) 批量入库 + AI 标注
        results = []
        original = (data.original_content or "").strip()
        for q in questions:
            # 题目内容：单题时把【原题】段提到前面
            # - 优先使用 AI 输出里的【原题】段（如果 AI 正确照抄了）
            # - 没有【原题】则用前端传来的 original_content 拼接
            q_content = q.get("content", "")
            q_answer = q.get("answer", "")
            q_analysis = q.get("analysis", "")
            q_knowledge = q.get("knowledge", "")
            orig_match = re.search(r"【原题】([\s\S]*?)(?:【答案】|$)", q_content)
            ai_original = orig_match.group(1).strip() if orig_match else ""
            # 决定最终原题
            final_original = ai_original if ai_original else original
            # 重组 content：原题在前 + 三段在后
            if final_original:
                if not has_marker and final_original not in q_content:
                    content_text = f"【原题】{final_original}\n\n" + q_content
                else:
                    content_text = q_content  # 多题时段里已含【原题】
            else:
                content_text = q_content
            # 自动标注（学科/知识点/错因）
            ann = await ai_service.annotate_mistake(content_text)
            cur = conn.execute(
                """INSERT INTO mistakes(category_id,subject,knowledge_point,error_cause,source,
                   content,answer,ai_analysis,created_at,updated_at)
                   VALUES(NULL,?,?,?,?,?,?,?,?,?)""",
                (
                    ann.get("subject", ""),
                    ann.get("knowledge_point", ""),
                    ann.get("error_cause", ""),
                    ann.get("source", "AI对话"),
                    content_text,
                    q.get("answer", ""),
                    q.get("analysis", "") or "",
                    db.now_str(),
                    db.now_str(),
                ),
            )
            conn.commit()
            new_id = cur.lastrowid
            row = conn.execute("SELECT * FROM mistakes WHERE id=?", (new_id,)).fetchone()
            results.append(dict(row))

        # 4) 关联关系：把本次录入的错题关联到这条消息（单题/多题都记录，便于追溯来源）
        if results:
            ids = ",".join(str(r["id"]) for r in results)
            try:
                conn.execute(
                    "INSERT INTO chat_conversions(message_id, mistake_ids, created_at) VALUES(?,?,?)",
                    (data.message_id, ids, db.now_str()),
                )
                conn.commit()
            except Exception:
                pass  # 表异常不影响主流程

        return {"items": results, "count": len(results)}
    finally:
        conn.close()
