"""DemoAgent —— capstone：把 NamiAgent 十一课收编成一个最小可读的 Agent

NamiAgent 一课加一个能力，这里是全部能力的合订本，砍掉三个集成层（聊天机器人、
定时心跳、MCP），只留 Agent 本体。每个模块对应一课，可与 lessons/lesson-NN 逐一对照：

    agent.py       第 1 课  最小循环：调模型 → 执行工具 → 结果回填 → 再调模型
    tools.py       第 2 课  装饰器注册表 + 内置工具
    permissions.py 第 3 课  硬规则 → 风险分级 → 人工确认（+第 10 课 plan 模式）
    context.py     第 4 课  截断 → 清理 → 摘要三层上下文 + 会话落盘恢复
    skills.py      第 5 课  技能清单进 system，load_skill 按需读全文
    subagent.py    第 9 课  delegate：独立上下文的子 Agent
    planning.py    第 10 课 update_plan 待办清单 + /plan 计划模式
    memory.py      第 11 课 MEMORY.md 长期记忆 + 会话原文检索

用法：
    pip install openai
    export API_KEY=ollama BASE_URL=http://127.0.0.1:11435/v1 MODEL=qwen3.8-27b
    python agent.py                 # 进入 REPL；/plan 任务 先计划后动手，exit 退出，重进可恢复
    python agent.py "一次性任务"     # 跑完即退

可选：工作区放 AGENTS.md（项目说明）和 skills/<名字>/SKILL.md（技能），启动时自动发现。

参考：NamiAgent（https://github.com/aa1143/NamiAgent）lesson-01/06/09/10/11
"""
import contextvars
import json
import os
import sys

from context import truncate_tool_result, clear_old_tool_results, compact, save_session
from permissions import PermissionManager
from tools import get_schemas, execute
import skills      # noqa: F401  导入即注册 load_skill
import subagent    # noqa: F401  导入即注册 delegate
import planning    # 注册 update_plan / submit_plan
import memory      # 注册 remember / search_sessions

MODEL = os.environ.get("MODEL", "deepseek-flash")
CURRENT = contextvars.ContextVar("current_run", default=None)   # 子 Agent/计划要知道"谁派的我"
MAX_STEPS = 20
SOFT_LIMIT = 16000   # 超过：清理旧工具结果
HARD_LIMIT = 24000   # 超过：摘要压缩

BASE_SYSTEM = ("你是一个能使用工具的助手，在用户的工作区内完成任务。"
               "必要时调用工具，完成后用简洁的语言汇报结果。")


def make_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["API_KEY"],
                  base_url=os.environ.get("BASE_URL", "https://api.deepseek.com"))


def build_system():
    return BASE_SYSTEM + skills.project_notes() + skills.skills_section() + memory.memory_section()


class Session:
    """一个会话 = 一份 messages + 一个权限管理器 + 上一次的 token 数
    tools 限定能用的工具（None 表示全部），system 可替换，depth 记录是第几层子 Agent"""

    def __init__(self, name, ask=None, persist=True, tools=None, system=None, depth=0):
        self.name = name
        self.persist = persist
        self.tools = set(tools) if tools is not None else None
        self.depth = depth
        saved = None
        if persist:
            from context import load_session
            saved = load_session(name)
        self.messages = saved or [{"role": "system", "content": ""}]
        self.messages[0] = {"role": "system", "content": system or build_system()}
        self.perms = PermissionManager(ask=ask)
        self.prompt_tokens = 0
        self.plan = []            # 最新一版待办清单

    def schemas(self):
        all_ = get_schemas()
        if self.tools is None:
            return all_
        return [s for s in all_ if s["function"]["name"] in self.tools]

    def save(self):
        if self.persist:
            save_session(self.name, self.messages)


def handle_call(call, perms, allowed=None):
    name = call.function.name
    if allowed is not None and name not in allowed:      # 模型请求了一个没发给它的工具
        return f"Error: 当前不能使用工具 {name}"
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Error: 参数不是合法的 JSON"
    decision = perms.check(name, args)
    if not decision.allowed:
        return f"[权限拒绝] {decision.reason}"
    return execute(name, args)


def run(session, user_input, client, model=MODEL, log=print, max_steps=MAX_STEPS):
    token = CURRENT.set((session, client, model, log))
    try:
        return _loop(session, user_input, client, model, log, max_steps)
    finally:
        CURRENT.reset(token)


def _loop(session, user_input, client, model, log, max_steps):
    messages = session.messages
    messages.append({"role": "user", "content": user_input})
    for _ in range(max_steps):
        # 用真实 token 数决定这一轮要不要先处理上下文（第 2 / 3 层）
        if session.prompt_tokens > HARD_LIMIT:
            messages[:] = compact(client, model, messages)
            log("📄 [上下文超硬限，已摘要压缩]")
        elif session.prompt_tokens > SOFT_LIMIT:
            clear_old_tool_results(messages)
            log("📄 [上下文超软限，已清理旧工具结果]")

        resp = client.chat.completions.create(model=model, messages=messages, tools=session.schemas())
        session.prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            log(f"🔧 {call.function.name}({call.function.arguments[:80]})")
            result = handle_call(call, session.perms, session.tools)
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": truncate_tool_result(result)})
    return "（达到最大步数，已停止）"


def main():
    client = make_client()
    session = Session("default")
    if len(session.messages) > 1:
        print(f"[恢复会话：{len(session.messages)} 条消息已从磁盘加载]")
    if len(sys.argv) > 1:                       # 一次性任务：跑完即退
        print("\n" + run(session, sys.argv[1], client) + "\n")
        session.save()
        return
    while True:                                 # REPL
        q = input("你> ").strip()
        if q in ("exit", "quit"):
            break
        if not q:
            continue
        if q.startswith("/plan "):              # 计划模式：进不进，由人决定
            q = planning.enter_plan_mode(session, q[len("/plan "):])
        print("\n" + run(session, q, client) + "\n")
        session.save()
    session.save()
    print("[会话已保存，下次启动自动恢复]")


if __name__ == "__main__":
    main()
