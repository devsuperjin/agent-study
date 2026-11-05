"""Day1：最小 Agent —— tool-calling 全链路 + 权限与安全边界

一条消息从 tools JSON 定义 → chat template 拼接 → 模型返回 tool_calls → 权限检查 → 本地执行 → 结果回填再调模型，
完整跑通最小 Agent 循环。配合 Modelfile（本地 GGUF 导入 Ollama）和 response.json（原始 HTTP 响应样例）学习。

权限三道关卡见 permissions.py：硬规则（工作区外路径、危险命令）→ 风险分级 → 人工确认。

用法：
    pip install openai
    export API_KEY=你的模型密钥
    python agent.py "在当前目录创建 hello.py，打印 hello，并运行它"

默认用 DeepSeek。换别的 OpenAI 兼容模型（如本地 Ollama），设置 BASE_URL 和 MODEL 两个环境变量即可。
工作区默认为当前目录，可用 AGENT_STUDY_WORKSPACE 覆盖。

参考：NamiAgent lesson-01（https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-01）
      NamiAgent lesson-03（permissions.py 模板）
"""
import json
import os
import subprocess
import sys

from openai import OpenAI

from permissions import PermissionManager, WORKSPACE, resolve_in_workspace

client = OpenAI(
    api_key=os.environ["API_KEY"],
    base_url=os.environ.get("BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.environ.get("MODEL", "deepseek-flash")
MAX_STEPS = 20  # 防止死循环：Agent 最多转 20 圈

SYSTEM = (
    "你是一个能操作本地文件和命令行的编程助手。"
    "需要时调用工具，完成任务后直接用文字总结，不要再调用工具。"
)


# ---------- 1. 工具：普通的 Python 函数，路径只认工作区 ----------
def read_file(path: str) -> str:
    p = resolve_in_workspace(path)
    if p is None:  # 双保险：即使绕过了权限检查，这里还会拦
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
    return (proc.stdout + proc.stderr)[-4000:] or "(无输出)"  # 截断，避免撑爆上下文


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
        args = json.loads(call.function.arguments)
    except json.JSONDecodeError:
        return "Error: 参数不是合法的 JSON"
    decision = perms.check(name, args)  # 硬规则 → 风险分级 → 人工确认
    if not decision.allowed:
        return f"[权限拒绝] {decision.reason}"
    try:
        return TOOL_FUNCS[name](**args)
    except Exception as e:  # 工具出错也要告诉模型，让它自己修正
        return f"工具执行出错：{type(e).__name__}: {e}"


# ---------- 2. 核心：Agent 循环 ----------
def run(task: str, perms: PermissionManager) -> None:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]
    for step in range(1, MAX_STEPS + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # 模型没有要调用工具 = 它认为任务做完了，循环结束
        if not msg.tool_calls:
            print(f"\n[完成，共 {step} 步]\n{msg.content}")
            return

        # 模型要调用工具：先过权限，再执行，并把结果作为 tool 消息喂回去
        for call in msg.tool_calls:
            name = call.function.name
            print(f"[第 {step} 步] {name}({call.function.arguments[:80]})")
            result = handle_call(call, perms)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    print(f"\n[达到 {MAX_STEPS} 步上限，已停止]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('用法：python agent.py "你的任务"')
    run(sys.argv[1], PermissionManager())
