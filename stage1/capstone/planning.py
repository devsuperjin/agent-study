"""planning.py —— 待办清单与计划模式

两样东西，解决两个不同的问题：
- update_plan：长任务做到一半忘了还剩什么。让模型把步骤写下来，每做完一步就更新。
- 计划模式：动手之前先让人看一眼方案。只读由权限层强制，计划经人批准才放行。

参考：NamiAgent lesson-10（https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-10）
"""
from tools import tool

STATUS = {"pending": "[ ]", "in_progress": "[→]", "completed": "[x]"}
PLAN_MARK = "[plan]"
OLD_PLAN = "[plan] 这是旧版计划，已被后面的版本取代"

PLAN_MODE_PREFIX = ("[计划模式] 先调查，不要修改任何东西（有副作用的工具会被拒绝）。"
                    "想清楚之后调用 submit_plan 提交一份分步骤的计划，等用户批准后再执行。\n任务：")


def _session():
    from agent import CURRENT                 # 延迟导入，避免循环引用
    cur = CURRENT.get()
    if cur is None:
        raise RuntimeError("只能在 Agent 运行时调用")
    return cur[0]


def render(steps):
    return "\n".join(f"{STATUS[s['status']]} {s['step']}" for s in steps)


@tool(
    name="update_plan",
    description=("记录或更新当前任务的分步计划。步骤超过 3 步的任务，开始前先写计划；"
                 "每完成一步就再调用一次，把状态改掉。同一时间最多一个步骤是 in_progress。"
                 "每次都传完整的步骤列表。"),
    parameters={"type": "object", "properties": {"steps": {
        "type": "array", "items": {"type": "object", "properties": {
            "step": {"type": "string"},
            "status": {"type": "string", "enum": list(STATUS)}},
            "required": ["step", "status"]}}},
        "required": ["steps"]},
)
def update_plan(steps):
    if not steps:
        return "Error: steps 不能为空"
    bad = [s for s in steps if s.get("status") not in STATUS or not s.get("step")]
    if bad:
        return f"Error: 步骤格式不对：{bad[0]}，status 只能是 {', '.join(STATUS)}"
    if sum(s["status"] == "in_progress" for s in steps) > 1:
        return "Error: 同一时间最多一个步骤是 in_progress"
    session = _session()
    session.plan = steps
    # 旧版本的计划在上下文里已经没用了，换成一句话，只留最新一版
    for m in session.messages:
        if m["role"] == "tool" and m["content"].startswith(PLAN_MARK):
            m["content"] = OLD_PLAN
    done = sum(s["status"] == "completed" for s in steps)
    return f"{PLAN_MARK} 当前计划（{done}/{len(steps)} 完成）\n{render(steps)}"


@tool(
    name="submit_plan",
    description="计划模式下使用：提交完整的执行计划给用户审批。批准后退出计划模式，可以开始修改。",
    parameters={"type": "object", "properties": {
        "plan": {"type": "string", "description": "分步骤的完整计划，写清要改哪些文件、怎么验证"}},
        "required": ["plan"]},
)
def submit_plan(plan):
    # 能走到这里，说明用户已经在确认界面看过计划并按了 y（submit_plan 是 CONFIRM 级）
    session = _session()
    if session.perms.mode != "plan":
        return "Error: 当前不在计划模式，直接执行即可"
    session.perms.mode = "normal"
    return "用户批准了计划。已退出计划模式，现在按计划执行；执行中如果需要偏离计划，先说明原因。"


def enter_plan_mode(session, task):
    """由用户触发（终端里输入 /plan 任务），不是给模型的工具：进不进计划模式，由人决定。"""
    session.perms.mode = "plan"
    return PLAN_MODE_PREFIX + task
