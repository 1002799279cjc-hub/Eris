"""导出服务：ReportLab 生成 PDF；同时提供 Markdown 导出。"""
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.pdfbase import pdfmetrics

from ..config import settings


def _escape(text: str) -> str:
    """PDF 文本转义（支持中文 + 特殊符号）。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sanitize(s: str) -> str:
    """导出 PDF 前清洗：去 LaTeX 残命令，把不易渲染的 Unicode 运算符替成 ASCII。"""
    if not s:
        return ''
    return (
        s.replace('\\boxed{', '').replace('}', '')
        .replace('\\text{', '').replace('\\bold{', '')
        .replace('\\quad', ' ').replace('\\,', ' ').replace('\\;', ' ')
        .replace('\\leq', '<=').replace('\\le', '<=')
        .replace('\\geq', '>=').replace('\\ge', '>=')
        .replace('\\neq', '!=').replace('\\ne', '!=')
        .replace('\\times', 'x').replace('\\cdot', '*')
        .replace('\\approx', '~=').replace('\\pm', '+/-')
        .replace('\\rightarrow', '->').replace('\\to', '->')
        .replace('\\infty', 'INF').replace('\\sum', 'SUM')
        .replace('\\dfrac{', '').replace('\\frac{', '/')
        .replace('\\sqrt{', 'sqrt(').replace('\\pi', 'pi')
        .replace('\\alpha', 'a').replace('\\beta', 'b').replace('\\theta', 'theta')
        .replace('\\\\', '\\').replace('\\(', '').replace('\\)', '')
        .replace('[', '').replace(']', '')
    )


def _load_font(prefer: str = "heiti") -> str:
    """多字体 fallback：黑体（字符覆盖最广）→ 宋体 → Helvetica。
    - 同一进程内已注册的字体直接复用
    - .ttc 字体需指定 subfontIndex=0
    """
    import os
    import traceback
    candidates = [
        ("CNHeiti",   "C:/Windows/Fonts/simhei.ttf",   None),
        ("CNYaHei",   "C:/Windows/Fonts/msyh.ttc",     0),
        ("CNYaHeiBd", "C:/Windows/Fonts/msyhbd.ttc",   0),
        ("CNSongti",  "C:/Windows/Fonts/simsun.ttc",   0),
        ("CNFangsong","C:/Windows/Fonts/simfang.ttf",  None),
        ("CNKaiti",   "C:/Windows/Fonts/simkai.ttf",    None),
    ]
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, path, sub_idx in candidates:
        if name in registered:
            return name
        if not os.path.exists(path):
            continue
        try:
            from reportlab.pdfbase.ttfonts import TTFont
            kwargs = {"subfontIndex": sub_idx} if sub_idx is not None else {}
            pdfmetrics.registerFont(TTFont(name, path, **kwargs))
            return name
        except Exception:
            print(f"[exporter] font register FAILED name={name} path={path}:")
            traceback.print_exc()
            continue
    return "Helvetica"


def export_pdf(mistakes: list[dict[str, Any]], title: str = "错题本导出") -> bytes:
    """ReportLab 渲染 PDF，返回字节流。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    font_name = _load_font("heiti")

    body = ParagraphStyle(
        "BodyCN", parent=styles["BodyText"], fontName=font_name,
        fontSize=10.5, leading=16, wordWrap="CJK",
    )
    h1 = ParagraphStyle("H1CN", parent=styles["Title"], fontName=font_name, fontSize=18)
    h2 = ParagraphStyle("H2CN", parent=styles["Heading2"], fontName=font_name, fontSize=13, spaceBefore=8)

    story: list[Any] = [Paragraph(_escape(title), h1), Spacer(1, 6)]
    story.append(Paragraph(
        f"导出时间：{datetime.now():%Y-%m-%d %H:%M}  共 {len(mistakes)} 题",
        ParagraphStyle("MetaCN", parent=styles["Normal"], fontName=font_name, fontSize=10),
    ))
    story.append(Spacer(1, 4))

    for m in mistakes:
        title_str = f"#{m['id']} [{m.get('subject', '')}] {m.get('knowledge_point', '')}"
        story.append(Paragraph(_escape(title_str), h2))
        story.append(Paragraph(f"<b>题目：</b>{_escape(_sanitize(m.get('content', '')))}", body))
        if m.get("answer"):
            story.append(Paragraph(f"<b>答案：</b>{_escape(_sanitize(m['answer']))}", body))
        if m.get("ai_analysis"):
            story.append(Paragraph(f"<b>AI解析：</b>{_escape(_sanitize(m['ai_analysis']))}", body))
        story.append(Paragraph(
            f"错因：{_sanitize(m.get('error_cause', '-'))}  来源：{_sanitize(m.get('source', '-'))}  "
            f"复习 {m.get('review_count', 0)} 次  状态：{'已掌握' if m.get('mastered') else '待复习'}",
            ParagraphStyle("MetaItem", parent=styles["Normal"], fontName=font_name, fontSize=9, textColor="#666"),
        ))
        story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()


def export_markdown(mistakes: list[dict[str, Any]], title: str = "错题本导出") -> str:
    """生成结构化 Markdown。"""
    lines = [f"# {title}", ""]
    lines.append(f"> 导出时间：{datetime.now():%Y-%m-%d %H:%M}　共 {len(mistakes)} 题")
    for m in mistakes:
        lines.append("")
        lines.append(f"## #{m['id']} [{m.get('subject','')}] {m.get('knowledge_point','')}")
        lines.append(f"- **题目**：{_sanitize(m.get('content',''))}")
        if m.get("answer"):
            lines.append(f"- **答案**：{_sanitize(m['answer'])}")
        if m.get("ai_analysis"):
            lines.append(f"- **AI解析**：{_sanitize(m['ai_analysis'])}")
        lines.append(f"- **错因**：{_sanitize(m.get('error_cause','-'))} ｜ **来源**：{_sanitize(m.get('source','-'))} ｜ "
                     f"**复习**：{m.get('review_count',0)} 次 ｜ **状态**：{'已掌握' if m.get('mastered') else '待复习'}")
    return "\n".join(lines)


def save_export(filename: str, data: bytes | str) -> str:
    """保存到 exports 目录，返回绝对路径。"""
    dest = settings.export_dir / filename
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(dest, mode, encoding="utf-8" if mode == "w" else None) as f:
        f.write(data)  # type: ignore[arg-type]
    return str(dest)
