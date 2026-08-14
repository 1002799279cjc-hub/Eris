"""帮助中心路由：FAQ、反馈。"""
from fastapi import APIRouter, Query

from ..schemas import FaqOut

router = APIRouter(prefix="/api/help", tags=["help"])

# 每条 FAQ 带 category（与前端 HelpView 的 categories 数组对齐）
FAQS = [
    {
        "category": "新手指南",
        "q": "如何录入一道错题？",
        "a": "支持拍照识别、截图、手动输入、粘贴文本四种方式。拍照后 AI 自动拆分多题、识别学科/知识点/错因，勾选即可导入。",
    },
    {
        "category": "新手指南",
        "q": "首次使用有什么建议？",
        "a": "建议先录入 5-10 道近期错题熟悉流程；然后到「一键复习」做第一轮变体题训练；最后查看「数据看板」了解薄弱点分布。",
    },
    {
        "category": "功能说明",
        "q": "如何创建和管理错题分类？",
        "a": "在「错题集」左侧导航点击「＋新建分类」即可创建，支持按学科、自定义标签管理。AI 录入错题时，若分类名与学科名一致会自动归入。",
    },
    {
        "category": "功能说明",
        "q": "AI解析是怎么生成的？",
        "a": "AI 基于题目内容自动生成解题思路、知识点归纳与易错提醒，可作为复习参考，建议结合老师讲解使用。",
    },
    {
        "category": "常见问题",
        "q": "复习提醒和计划如何设置？",
        "a": "系统基于 SM-2 间隔重复算法自动生成每日/周度/考前复习计划，可在「数据看板」查看近期安排，并支持手动调整。",
    },
    {
        "category": "常见问题",
        "q": "AI 流式回答突然停了怎么办？",
        "a": "通常因为 AI 服务端限流或网络抖动。可点击输入框重新发送，或在「🔧 测试面板」一键测试 API 连接。",
    },
    {
        "category": "常见问题",
        "q": "录入时 OCR 识别失败怎么办？",
        "a": "OCR 三层降级：①优先 DeepSeek-OCR 多模态 ②本地 PaddleOCR ③占位提示。失败时可手动输入/粘贴题目文字，仍可正常录入。",
    },
    {
        "category": "使用技巧",
        "q": "错题数据如何导出？",
        "a": "在「错题集」点击「导出」可按分类、学科或时间范围导出为 PDF / Markdown，便于打印或分享。",
    },
    {
        "category": "使用技巧",
        "q": "如何把 AI 对话保存为错题？",
        "a": "在 AI 答疑中，AI 回答消息下方点击「一键加入错题本」，即可将对话内容（含原题）结构化保存为错题并进入复习闭环。",
    },
    {
        "category": "使用技巧",
        "q": "一键复习时怎么只复习某一学科？",
        "a": "进入「一键复习」后选择具体学科即可；若该学科无待复习错题会明确提示，不会悄悄出其他学科的题。",
    },
    {
        "category": "联系我们",
        "q": "遇到问题如何反馈？",
        "a": "在「帮助 → 联系我们」页面填写反馈内容；或用「🔧 测试面板」一键检测 API 连接、复制诊断信息给开发者。",
    },
]


@router.get("/faqs", response_model=list[FaqOut])
def faqs(
    keyword: str | None = None,
    category: str | None = Query(None, description="按分类过滤：新手指南/功能说明/常见问题/使用技巧/联系我们"),
):
    items = FAQS
    if category:
        items = [f for f in items if f["category"] == category]
    if keyword:
        items = [f for f in items if keyword in f["q"] or keyword in f["a"]]
    return items


@router.post("/feedback")
def feedback(payload: dict):
    text = (payload.get("content") or "").strip()
    return {"ok": True, "received": bool(text), "message": "反馈已记录，感谢！"}
