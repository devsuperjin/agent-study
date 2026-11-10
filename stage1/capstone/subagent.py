"""subagent.py —— 子 Agent（capstone 简化版：只保留 delegate）

子 Agent 就是一个新的 Session：自己的 messages、自己的工具清单、自己的步数上限。
父 Agent 只拿回它最后的一段文字，中间读了多少文件、试错了多少次，都不进父 Agent 的上下文。

参考：NamiAgent lesson-09（https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-09）
"""
from permissions import TOOL_RISK, Risk
from tools import TOOLS, tool

MAX_DEPTH = 1            # 只允许一层：子 Agent 不能再派子 Agent
SUB_MAX_STEPS = 15
RESULT_LIMIT = 3000      # 子 Agent 交回来的结论最多这么长

# 这些工具子 Agent 永远拿不到：派生、计划、记忆都只能由主 Agent 做
NEVER_FOR_SUB = {"delegate", "submit_plan", "remember"}

SUB_SYSTEM = ("你是一个子 Agent，被主 Agent 派来完成一件具体的事。"
              "你看不到主 Agent 和用户之前的对话，只能根据下面的任务说明行动。"
              "完成后用简洁的文字汇报结论，写清楚依据（读了哪些文件、看到了什么），"
              "不要贴大段原文。做不到就直接说明原因。")


def toolset(kind):
    """explore：只拿只读工具；worker：除了派生/计划/记忆之外的全部工具。"""
    names = set(TOOLS) - NEVER_FOR_SUB
    if kind == "explore":
        names = {n for n in names if TOOL_RISK.get(n) is Risk.SAFE}
    return names


def _current():
    from agent import CURRENT                 # 延迟导入，避免和 agent.py 循环引用
    cur = CURRENT.get()
    if cur is None:
        raise RuntimeError("只能在 Agent 运行时调用")
    parent, client, model, log = cur
    if parent.depth >= MAX_DEPTH:
        raise RuntimeError("子 Agent 不能再派生子 Agent")
    return parent, client, model, log


def _spawn(task, kind, parent, client, model, log):
    from agent import Session, run
    tag = "子Agent"
    sub = Session(f"{parent.name}/{tag}", ask=parent.perms.ask, persist=False,
                  tools=toolset(kind), system=SUB_SYSTEM, depth=parent.depth + 1)
    sub.perms.mode = parent.perms.mode       # 计划模式下派出去的子 Agent 也只能读
    try:
        result = run(sub, task, client, model,
                     log=lambda m: log(f"  [{tag}] {m}"), max_steps=SUB_MAX_STEPS)
    except Exception as e:
        return f"[{tag} 出错] {type(e).__name__}: {e}"
    if len(result) > RESULT_LIMIT:
        result = result[:RESULT_LIMIT] + "\n...（子 Agent 的结论过长，已截断）"
    return f"[{tag} 的结论]\n{result}"


@tool(
    name="delegate",
    description=("把一件边界清楚的子任务交给一个子 Agent。它有独立的上下文，看不到当前对话，"
                 "所以 task 里要写清目标、范围和希望交回的格式。"
                 "kind=explore 只能读（查资料、读代码、找文件），kind=worker 还能写文件和执行命令，"
                 "每个有副作用的操作照样需要用户确认。适合：要读很多内容但只需要结论的任务。"),
    parameters={"type": "object", "properties": {
        "task": {"type": "string", "description": "完整的任务说明"},
        "kind": {"type": "string", "enum": ["explore", "worker"]}},
        "required": ["task"]},
)
def delegate(task, kind="explore"):
    try:
        parent, client, model, log = _current()
    except RuntimeError as e:
        return f"Error: {e}"
    return _spawn(task, kind, parent, client, model, log)
