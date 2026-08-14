"""数据看板路由：KPI、录入趋势、学科分布、错因分布、薄弱 TOP5、近期计划。"""
from datetime import date, timedelta

from fastapi import APIRouter

from ..schemas import ERROR_CAUSES

from .. import database as db
from ..schemas import ItemValue, KpiOut, PlanItem, TrendPoint

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _since_days(rng: str) -> int:
    return {"30d": 30, "term": 120, "all": 3650}.get(rng, 30)


@router.get("/summary", response_model=KpiOut)
def summary(rng: str = "30d"):
    conn = db.get_conn()
    try:
        since = (date.today() - timedelta(days=_since_days(rng))).isoformat()
        total = conn.execute(
            "SELECT COUNT(*) FROM mistakes WHERE date(created_at)>=?", (since,)
        ).fetchone()[0]
        mastered = conn.execute(
            "SELECT COUNT(*) FROM mistakes WHERE mastered=1 AND date(created_at)>=?", (since,)
        ).fetchone()[0]
        pending = total - mastered
        rate = round(mastered * 100 / total) if total else 0
        return {"total": total, "mastered": mastered, "pending": pending, "mastery_rate": rate}
    finally:
        conn.close()


@router.get("/trend", response_model=list[TrendPoint])
def trend(days: int = 30):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT date(created_at) AS d, COUNT(*) AS n FROM mistakes
               WHERE date(created_at)>=date('now',?||' days')
               GROUP BY d ORDER BY d""",
            (-days,),
        ).fetchall()
        data = {r["d"]: r["n"] for r in rows}
        out = []
        for i in range(days - 1, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            out.append({"label": d[5:], "value": data.get(d, 0)})
        return out
    finally:
        conn.close()


@router.get("/subjects", response_model=list[ItemValue])
def subjects():
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT subject, COUNT(*) AS n FROM mistakes GROUP BY subject ORDER BY n DESC"
        ).fetchall()
        palette = ["#E4002B", "#141414", "#003DA5", "#FFCE00", "#6b6b6b", "#c40025"]
        return [{"label": r["subject"], "value": r["n"], "color": palette[i % len(palette)]}
                for i, r in enumerate(rows)]
    finally:
        conn.close()


@router.get("/causes", response_model=list[ItemValue])
def causes():
    """错因分布：固定 5 个错因（保持看板稳定），count=0 的也返回，便于实时刷新占位。"""
    conn = db.get_conn()
    try:
        # 聚合每个固定错因的真实计数
        rows = conn.execute(
            "SELECT error_cause, COUNT(*) AS n FROM mistakes WHERE error_cause IN ({}) GROUP BY error_cause".format(
                ",".join("?" * len(ERROR_CAUSES))
            ),
            ERROR_CAUSES,
        ).fetchall()
        counts = {r["error_cause"]: r["n"] for r in rows}
        # 5 种固定颜色循环（与错题录入趋势图/学科图协调）
        palette = ["#E4002B", "#003DA5", "#FFCE00", "#141414", "#6b6b6b"]
        return [
            {"label": c, "value": counts.get(c, 0), "color": palette[i % len(palette)]}
            for i, c in enumerate(ERROR_CAUSES)
        ]
    finally:
        conn.close()


@router.get("/weak-top", response_model=list[ItemValue])
def weak_top(limit: int = 5):
    """薄弱知识点 TOP：按未掌握数降序、未掌握率降序、错误数降序、知识点字母序，确保稳定排序。"""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT knowledge_point AS kp, COUNT(*) AS n,
                      SUM(CASE WHEN mastered=0 THEN 1 ELSE 0 END) AS bad
               FROM mistakes WHERE knowledge_point<>''
               GROUP BY knowledge_point
               ORDER BY bad DESC, (bad*1.0/n) DESC, n DESC, kp ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        palette = ["#E4002B", "#003DA5", "#141414", "#FFCE00", "#6b6b6b"]
        out = []
        for i, r in enumerate(rows):
            ratio = (r["bad"] / r["n"] * 100) if r["n"] else 0
            out.append({"label": r["kp"], "value": round(ratio), "color": palette[i % len(palette)]})
        return out
    finally:
        conn.close()


@router.get("/plans", response_model=list[PlanItem])
def upcoming_plans(days: int = 7):
    conn = db.get_conn()
    try:
        since = date.today().isoformat()
        until = (date.today() + timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT p.due_date AS d, m.subject, m.knowledge_point, COUNT(*) AS n
               FROM review_plans p JOIN mistakes m ON m.id=p.mistake_id
               WHERE p.due_date BETWEEN ? AND ? AND p.status='pending'
               GROUP BY p.due_date, m.subject, m.knowledge_point ORDER BY p.due_date""",
            (since, until),
        ).fetchall()
        return [{"date": r["d"], "subject": r["subject"], "knowledge_point": r["knowledge_point"],
                 "pending": r["n"]} for r in rows]
    finally:
        conn.close()
