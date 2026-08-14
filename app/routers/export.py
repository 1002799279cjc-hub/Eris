"""导出路由：PDF（ReportLab）/ Markdown / Excel 视图。"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import database as db
from ..schemas import ExportIn, ExportOut
from ..services import exporter

router = APIRouter(prefix="/api/export", tags=["export"])


def _query_mistakes(data: ExportIn) -> list[dict]:
    conn = db.get_conn()
    try:
        where, params = ["1=1"], []
        if data.category_id:
            where.append("category_id=?"); params.append(data.category_id)
        if data.subject:
            where.append("subject=?"); params.append(data.subject)
        if data.date_from:
            where.append("date(created_at)>=?"); params.append(data.date_from)
        if data.date_to:
            where.append("date(created_at)<=?"); params.append(data.date_to)
        rows = conn.execute(
            f"SELECT * FROM mistakes WHERE {' AND '.join(where)} ORDER BY id",
            params,
        ).fetchall()
        return db.rows_to_dicts(rows)
    finally:
        conn.close()


@router.post("/pdf", response_model=ExportOut)
def export_pdf(data: ExportIn):
    mistakes = _query_mistakes(data)
    if not mistakes:
        raise HTTPException(400, "没有可导出的错题")
    pdf = exporter.export_pdf(mistakes, title="Recall 错题本导出")
    filename = f"recall_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = exporter.save_export(filename, pdf)
    return {"filename": filename, "path": path}


@router.post("/markdown", response_model=ExportOut)
def export_markdown(data: ExportIn):
    """评审砍项：Markdown 导出已从产品移除（学生无场景）。
    端点保留仅用于内部调试，前端不再暴露入口。"""
    mistakes = _query_mistakes(data)
    if not mistakes:
        raise HTTPException(400, "没有可导出的错题")
    md = exporter.export_markdown(mistakes)
    filename = f"recall_{datetime.now():%Y%m%d_%H%M%S}.md"
    path = exporter.save_export(filename, md)
    return {"filename": filename, "path": path}


@router.get("/download/{filename}")
def download(filename: str):
    """按文件名下载已导出文件（防路径穿越）。"""
    safe = filename.replace("/", "").replace("\\", "")
    file = exporter.settings.export_dir / safe
    if not file.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file, filename=safe)
