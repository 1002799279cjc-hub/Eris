"""DeepSeek AI 服务封装。
- 配置了 DEEPSEEK_API_KEY：走真实 OpenAI 兼容流式调用。
- 未配置：自动降级为 Mock，返回可演示的结构化结果，保证全站可用。
"""
import json
import re
from typing import Any, AsyncIterator

from ..config import settings
from ..schemas import ERROR_CAUSES

# 学科与错因已统一在 schemas


SUBJECTS = ["数学", "语文", "英语", "物理", "化学", "生物"]


def _subject_fallback(text: str) -> str:
    for s in SUBJECTS:
        if s in text:
            return s
    return "数学"


def _parse_json_loose(text: str) -> dict[str, Any]:
    """从 AI 输出中尽力提取 JSON 对象。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


class AIService:
    def __init__(self) -> None:
        self._client = None
        self._reload_client()

    def _reload_client(self) -> None:
        """按当前 settings 重建 OpenAI 客户端（支持运行时切换 Key）。"""
        self._client = None
        if settings.ai_enabled:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                )
            except Exception:
                self._client = None

    def configure(self, api_key: str, model: str = "") -> str:
        """运行时配置 Key 与模型并持久化，返回新的运行模式。
        先做格式预检：无效 Key 抛 ValueError（调用方应捕获并保持原配置），防止污染运行时。
        """
        from ..config import BASE_DIR
        key = (api_key or "").strip()
        # N3 修复：格式预检（sk- 前缀 + 最小长度），无效立即拒绝
        if not key.startswith("sk-") or len(key) < 20:
            raise ValueError("Key 格式无效：应以 sk- 开头且长度不少于 20 字符")
        settings.deepseek_api_key = key
        if model.strip():
            settings.deepseek_model = model.strip()
        settings_file = BASE_DIR / "data" / "settings.json"
        try:
            settings_file.write_text(
                json.dumps(
                    {
                        "deepseek_api_key": settings.deepseek_api_key,
                        "deepseek_model": settings.deepseek_model,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        self._reload_client()
        return self.mode

    @property
    def mode(self) -> str:
        return "deepseek" if self._client else "mock"

    @property
    def has_key(self) -> bool:
        return bool(settings.deepseek_api_key)

    @property
    def model_name(self) -> str:
        return settings.deepseek_model

    # ---------- 文本补全（流式） ----------
    # 统一数学格式约束：避免 LaTeX 命令导致前端出现无法理解的符号
    MATH_RULE = (
        "数学公式请用纯文本表示，禁止使用任何 LaTeX 命令（如 \\boxed \\quad \\text \\bold "
        "\\( \\) \\[ \\] \\begin \\frac \\sqrt \\times \\le \\ge 等）。"
        "规则：平方写 x^2，下标写 a_1，分数写 (a)/(b)，乘号写 *，根号写 sqrt(2)，"
        "空行分隔段落，每步推导用数字编号。"
    )
    # 结构化输出 + 不展示思考过程
    STRUCTURE_RULE = (
        "直接给答案，禁止输出思考过程/反问/自言自语。"
        "根据用户提问的字数智能判断题目数量：\n"
        "【单题】严格按以下四段结构输出（中文标点），务必先照抄原题再作答：\n"
        "【原题】用户给出的题目原文一字不漏地照抄一遍（题目号、选项 A/B/C/D、子题 (1)(2)、图表描述等都不能省略）。\n"
        "【答案】一行以内的核心结论。\n"
        "【答案解析】分1. 2. 3. 简短步骤，每步一行。\n"
        "【对应知识点】一句话列出考点。\n"
        "【多题】每题都用以下四段格式（先照抄题目再作答），题间用 ### 问题 N 分隔：\n"
        "### 问题 1\n"
        "【原题】该题目的完整原文（含选项/子题）。\n"
        "【答案】...\n"
        "【答案解析】...\n"
        "【对应知识点】...\n"
        "\n"
        "### 问题 2\n"
        "【原题】...\n"
        "【答案】...\n"
        "【答案解析】...\n"
        "【对应知识点】...\n"
        "\n"
        "### 问题 3\n"
        "（同上结构）\n"
        "【题不清时主动说明】如果题目本身残缺（如大量 `*****` `?????` `~~~~~~~~` `_____` 占位/缺字、关键信息缺失），"
        "在【答案解析】开头明确说「题目残缺：用户给的题目中含有大量占位/缺字…」并列出能识别出的部分，"
        "不要硬猜或假装看懂。\n"
        "禁止使用 --- 等分隔符，禁止使用全角括号包裹数学符号，禁止使用 # 标题。"
    )

    async def stream_chat(
        self, messages: list[dict[str, str]], system: str = ""
    ) -> AsyncIterator[str]:
        if self._client:
            sys_msg = system or "你是耐心的中学全科答疑老师。"
            sys_msg += "\n" + self.STRUCTURE_RULE + "\n" + self.MATH_RULE
            full = [{"role": "system", "content": sys_msg}] + messages
            try:
                stream = await self._client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=full,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                return
            except Exception:
                yield self.mock_answer(messages[-1]["content"])
                return
        # Mock：按停顿切分，模拟流式
        answer = self.mock_answer(messages[-1]["content"])
        for i in range(0, len(answer), 12):
            yield answer[i:i + 12]

    def mock_answer(self, question: str) -> str:
        if "函数" in question or "最值" in question or "二次" in question:
            return (
                "【Mock 演示回答】这是二次函数在闭区间求最值的经典题。\n\n"
                "1. 配方：f(x) = (x-a)² + (3-a²)\n"
                "2. 对称轴 x=a，与区间[1,2]的位置关系分三种情况：\n"
                "   · a≤1：区间内单调递增，最小值 f(1)=4-2a\n"
                "   · 1<a<2：最小值在顶点取得 f(a)=3-a²\n"
                "   · a≥2：区间内单调递减，最小值 f(2)=7-4a\n"
                "3. 令最小值=2 分别求解，取符合区间条件的解。\n\n"
                "提示：配置 DEEPSEEK_API_KEY 后由真实模型作答。"
            )
        return (
            f"【Mock 演示回答】针对你的问题「{question[:40]}…」\n\n"
            "这是一个很好的提问。建议从以下角度思考：\n"
            "1. 先定位该题考察的知识点与常见题型；\n"
            "2. 拆解题目条件，列出已知与待求；\n"
            "3. 套用对应模型/公式，注意边界条件；\n"
            "4. 最后验证答案是否符合常识。\n\n"
            "提示：配置 DEEPSEEK_API_KEY 后由真实模型作答。"
        )

    # ---------- 结构化任务（错题标注 / 解析 / 变体 / 批改） ----------
    async def annotate_mistake(self, content: str) -> dict[str, Any]:
        """识别学科 / 知识点 / 错因 / 分类建议。"""
        if self._client:
            try:
                resp = await self._client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": (
                            "你是错题分析助手。请对给出的题目输出 JSON，字段："
                            '{"subject":"学科","knowledge_point":"知识点","error_cause":"错因","source":"来源"}'
                            "。只输出 JSON。"
                        )},
                        {"role": "user", "content": content[:2000]},
                    ],
                    temperature=0.2,
                )
                data = _parse_json_loose(resp.choices[0].message.content or "")
                if data:
                    return data
            except Exception:
                pass
        return {
            "subject": _subject_fallback(content),
            "knowledge_point": "函数与最值" if "函数" in content else "综合",
            "error_cause": ERROR_CAUSES[0],
            "source": "手动录入",
        }

    async def ai_analysis(self, content: str, answer: str = "") -> str:
        if self._client:
            try:
                resp = await self._client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": (
                            "你是金牌解题教练。"
                            + self.STRUCTURE_RULE
                            + self.MATH_RULE
                        )},
                        {"role": "user", "content": f"题目：{content}\n参考答案：{answer or '无'}"},
                    ],
                )
                return resp.choices[0].message.content or self.mock_answer(content)
            except Exception:
                pass
        return self.mock_answer(content)

    async def generate_variant(self, mistake: dict[str, Any]) -> str:
        if self._client:
            try:
                resp = await self._client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": (
                            "你是命题老师。基于原题生成一道同考点、同难度的变体题，"
                            "只输出题目本身（含选项或填空），不要解析。"
                        )},
                        {"role": "user", "content": f"原题：{mistake['content']}\n知识点：{mistake['knowledge_point']}"},
                    ],
                )
                return resp.choices[0].message.content or ""
            except Exception:
                pass
        return (
            f"【变体题】已知函数 g(x)=x²-2bx+3 在区间 [1,2] 上的最大值为 3，求实数 b 的取值范围。"
            f"（同考点：{mistake.get('knowledge_point', '二次函数最值')} 的变式训练）"
        )

    async def grade_answer(self, question: str, user_answer: str, reference: str = "") -> dict[str, Any]:
        if self._client:
            try:
                resp = await self._client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": (
                            "你是批改老师。输出 JSON：{\"score\":0~100,\"passed\":true/false,\"comment\":\"评语\"}"
                        )},
                        {"role": "user", "content": f"题目：{question}\n学生答案：{user_answer}\n参考：{reference}"},
                    ],
                )
                data = _parse_json_loose(resp.choices[0].message.content or "")
                if data:
                    score = max(0, min(100, int(data.get("score", 0))))
                    return {
                        "score": score,
                        "passed": bool(data.get("passed", score >= 60)),
                        "comment": data.get("comment", "已批改。"),
                    }
            except Exception:
                pass
        import random
        score = random.randint(40, 100)
        return {
            "score": score,
            "passed": score >= 60,
            "comment": "【Mock 批改】已自动判分。配置 DEEPSEEK_API_KEY 后可获得逐点批改评语。",
        }


def _load_persisted_key() -> None:
    """启动时读取持久化的 Key 与模型（测试面板配置过的话重启不丢失）。"""
    try:
        from ..config import BASE_DIR
        f = BASE_DIR / "data" / "settings.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("deepseek_api_key"):
                settings.deepseek_api_key = data["deepseek_api_key"].strip()
            if data.get("deepseek_model"):
                settings.deepseek_model = data["deepseek_model"].strip()
    except Exception:
        pass


_load_persisted_key()
ai_service = AIService()
