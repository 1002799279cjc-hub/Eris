"""SM-2 间隔重复算法：决定每题复习间隔与到期时间。"""
from dataclasses import dataclass


@dataclass
class SM2State:
    ease_factor: float = 2.5      # 难度系数
    interval: int = 0             # 当前间隔（天）
    reps: int = 0                 # 连续通过次数
    due_days: int = 0             # 距下次复习天数


def initial_state() -> SM2State:
    return SM2State()


def review(state: SM2State, quality: int) -> SM2State:
    """quality: 0(完全忘记)~5(完美作答)。按 SM-2 规则更新状态。"""
    q = max(0, min(5, quality))
    if q < 3:
        state.reps = 0
        state.interval = 1
    else:
        if state.reps == 0:
            state.interval = 1
        elif state.reps == 1:
            state.interval = 6
        else:
            state.interval = round(state.interval * state.ease_factor)
        state.reps += 1
    state.ease_factor = max(
        1.3, state.ease_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    )
    state.due_days = state.interval
    return state


def plan_type_for(interval: int) -> str:
    """按间隔归类计划类型：day / week / exam。"""
    if interval <= 1:
        return "day"
    if interval <= 7:
        return "week"
    return "exam"
