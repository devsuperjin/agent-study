"""Day2：状态、上下文与持久化

在 Day1 最小循环之上加三件事：
1. 上下文管理：按真实 prompt token 数分级处理——超软限清理旧工具结果，超硬限摘要压缩
2. 会话持久化：每轮存盘，下次启动自动恢复（interrupt and resume）
3. 权限与安全边界：permissions.py 三道关卡（硬规则 → 风险分级 → 人工确认），与 day1 同一套

用法：
    pip install openai
    export API_KEY=ollama BASE_URL=http://127.0.0.1:11435/v1 MODEL=qwen3.8-27b
    python agent.py          # 进入 REPL，exit/quit 退出；再进来上下文还在

参考：NamiAgent lesson-04（https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-04）
      NamiAgent lesson-03（permissions.py 模板）
"""
import json
import os
import subprocess
import sys

from openai import OpenAI

from context import (truncate_tool_result, clear_old_tool_results, compact,
                     save_session, load_session)
from permissions import PermissionManager, WORKSPACE, resolve_in_workspace

client = OpenAI(
    api_key=os.environ["API_KEY"],
    base_url=os.environ.get("BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.environ.get("MODEL", "deepseek-flash")
MAX_STEPS = 20
SOFT_LIMIT = 16000   # 超过：清理旧工具结果
HARD_LIMIT = 24000   # 超过：摘要压缩
# 演示用的小值，方便复现；实际按模型窗口比例设

SESSION_NAME = "default"
SYSTEM = (
    "你是一个能操作本地文件和命令行的编程助手。"
    "需要时调用工具，完成任务后直接用文字总结，不要再调用工具。"
)


# ---------- 工具：与 Day1 相同的三个，路径只认工作区 ----------
def read_file(path: str) -> str:
    p = resolve_in_workspace(path)
    if p is None:
        return f"[错误] 路径在工作区之外：{path}"
    return p.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    p = resolve_in_workspace(path)
    if p is None:
        return f"[错误] 路径在工作区之外：{path}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {p.relative_to(WORKSPACE)}（{len(content)} 字符）"


def run_shell(command: str) -> str:
    try:
        proc = subprocess.run(command, shell=True, cwd=WORKSPACE,
                              capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "命令超时（60 秒）"
    return (proc.stdout + proc.stderr)[-4000:] or "(无输出)"


def _tool(name, desc, props):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
                "required": list(props),
            },
        },
    }


TOOLS = [
    _tool("read_file", "读取文件内容", {"path": "文件路径"}),
    _tool("write_file", "写入文件（覆盖）", {"path": "文件路径", "content": "完整文件内容"}),
    _tool("run_shell", "执行 shell 命令并返回输出", {"command": "要执行的命令"}),
]

TOOL_FUNCS = {"read_file": read_file, "write_file": write_file, "run_shell": run_shell}


def handle_call(call, perms: PermissionManager) -> str:
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Error: 参数不是合法的 JSON"
    decision = perms.check(name, args)  # 硬规则 → 风险分级 → 人工确认
    if not decision.allowed:
        return f"[权限拒绝] {decision.reason}"
    try:
        return TOOL_FUNCS[name](**args)
    except Exception as e:
        return f"工具执行出错：{type(e).__name__}: {e}"


# ---------- Agent 循环：按 token 数分级的上下文处理 + 权限检查 ----------
def run(user_input: str, messages: list, perms: PermissionManager) -> str:
    messages.append({"role": "user", "content": user_input})
    for step in range(1, MAX_STEPS + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or ""

        for call in msg.tool_calls:
            name = call.function.name
            print(f"[第 {step} 步] {name}({call.function.arguments[:80]}) [prompt_tokens={prompt_tokens}]")
            result = handle_call(call, perms)
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": truncate_tool_result(result)})   # 第 1 层
            prompt_tokens += len(result) // 4   # 粗估工具结果带来的增量

        # 用真实 token 数决定下一轮要不要处理（第 2 / 3 层）
        if prompt_tokens > HARD_LIMIT:
            messages[:] = compact(client, MODEL, messages)
            print("[上下文超硬限，已摘要压缩]")
        elif prompt_tokens > SOFT_LIMIT:
            clear_old_tool_results(messages)
            print("[上下文超软限，已清理旧工具结果]")
    return "（达到最大步数，已停止）"


def main():
    # clock in：从磁盘恢复会话；没有则用全新 system prompt
    messages = load_session(SESSION_NAME) or [{"role": "system", "content": SYSTEM}]
    perms = PermissionManager()  # "本次会话一直允许"的记忆在整个 REPL 生命周期内有效
    if len(messages) > 1:
        print(f"[恢复会话：{len(messages)} 条消息已从磁盘加载]")
    while True:
        try:
            q = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q in ("exit", "quit"):
            break
        if not q:
            continue
        print("\n" + run(q, messages, perms) + "\n")
        # clock out：每轮结束落盘，随时可中断、随时可恢复
        save_session(SESSION_NAME, messages)
    save_session(SESSION_NAME, messages)
    print(f"[会话已保存：{SESSION_NAME}.json，下次启动自动恢复]")


if __name__ == "__main__":
    main()
