"""SQLite 数据库：连接、建表、种子数据。使用标准库 sqlite3，零额外依赖。"""
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL DEFAULT '#141414',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mistakes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER,
  subject TEXT NOT NULL DEFAULT '',
  knowledge_point TEXT NOT NULL DEFAULT '',
  error_cause TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  answer TEXT NOT NULL DEFAULT '',
  ai_analysis TEXT NOT NULL DEFAULT '',
  image_path TEXT NOT NULL DEFAULT '',
  review_count INTEGER NOT NULL DEFAULT 0,
  mastered INTEGER NOT NULL DEFAULT 0,
  reviewed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (category_id) REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS review_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mistake_id INTEGER NOT NULL,
  due_date TEXT NOT NULL,
  plan_type TEXT NOT NULL DEFAULT 'day',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id)
);
CREATE TABLE IF NOT EXISTS review_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mistake_id INTEGER NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  passed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id)
);
CREATE TABLE IF NOT EXISTS chat_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL DEFAULT '新对话',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);
CREATE TABLE IF NOT EXISTS chat_conversions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER NOT NULL,
  mistake_ids TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

SEED_CATEGORIES = [
    ("数学", "#E4002B", 1), ("语文", "#141414", 2), ("英语", "#003DA5", 3),
    ("物理", "#003DA5", 4), ("化学", "#E4002B", 5), ("生物", "#FFCE00", 6),
]

SEED_MISTAKES = [
    (1, "数学", "二次函数最值", "知识点薄弱", "2024高考真题",
     "已知函数 f(x)=x²-2ax+3，若 f(x) 在区间 [1,2] 上的最小值为 2，求实数 a 的取值范围。",
     "配方 f(x)=(x-a)²+(3-a²)，按对称轴与区间位置分三种情况讨论，解得 a=1。", 3, 1, 1, "2026-08-10 10:00"),
    (5, "生物", "细胞呼吸", "理解偏差", "模拟考试",
     "下列关于人体细胞呼吸的叙述，正确的是（ ）A.无氧呼吸不需要氧气直接参与 B.有氧呼吸只在线粒体中进行 C.乳酸菌只能进行无氧呼吸 D.酵母菌在有氧条件下进行有氧呼吸。",
     "选 A。注意无氧呼吸第一阶段在细胞质基质中进行，有氧呼吸第一阶段也在细胞质基质。", 1, 0, 1, "2026-08-09 20:15"),
    (2, "语文", "文本理解", "粗心大意", "课后练习",
     "阅读《岳阳楼记》选段，回答：作者借「古仁人」的形象表达了怎样的人生理想？请结合全文简要分析。",
     "先天下之忧而忧，后天下之乐而乐；答题模板：形象概括+情感表达+现实意义。", 5, 1, 0, "2026-08-07 16:42"),
    (3, "英语", "阅读理解", "理解偏差", "月考试卷",
     'In the passage, the author uses the word "resilience" to _____. What is the main idea of paragraph 3?',
     "定位段首主旨句，注意转折词 however / but 之后往往是作者真实观点。", 2, 0, 0, "2026-08-05 19:33"),
]

SEED_CHATS = [
    (1, "二次函数求最值问题", "2026-08-12 14:30"),
    (2, "细胞呼吸相关疑问", "2026-08-11 20:15"),
]
SEED_MESSAGES = [
    (1, "user", "二次函数 f(x)=x²-2ax+3 在[1,2]上最小值为2，怎么求 a 的范围？"),
    (1, "assistant", "关键讨论对称轴 x=a 与区间[1,2]的位置关系：①a≤1 单调增 f(1)=2；②1<a<2 取顶点；③a≥2 单调减 f(2)=2。综上 a=1。"),
    (2, "user", "细胞呼吸和光合作用的联系是什么？"),
    (2, "assistant", "两者通过 ATP 和 NADPH/NADH 间接联系：光合作用储存能量，呼吸作用释放能量，共同维持细胞内能量代谢平衡。"),
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_str() -> str:
    return date.today().isoformat()


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # 种子分类
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO categories(name,color,sort_order,created_at) VALUES(?,?,?,?)",
                [(n, c, s, now_str()) for n, c, s in SEED_CATEGORIES],
            )
        # 种子错题
        if conn.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0] == 0:
            conn.executemany(
                """INSERT INTO mistakes(category_id,subject,knowledge_point,error_cause,source,
                   content,answer,review_count,mastered,reviewed,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(c, s, k, e, src, content, ans, rc, m, rv, t, t)
                 for c, s, k, e, src, content, ans, rc, m, rv, t in SEED_MISTAKES],
            )
        # 种子对话
        if conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 0:
            session_map: dict[int, int] = {}
            for sid, title, t in SEED_CHATS:
                cur = conn.execute(
                    "INSERT INTO chat_sessions(title,created_at,updated_at) VALUES(?,?,?)",
                    (title, t, t),
                )
                session_map[sid] = cur.lastrowid
            for sid, role, content in SEED_MESSAGES:
                conn.execute(
                    "INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                    (session_map[sid], role, content, now_str()),
                )
        conn.commit()
    finally:
        conn.close()
