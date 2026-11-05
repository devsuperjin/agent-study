"""context.py —— Day2：状态、上下文与持久化

上下文管理三层：截断工具结果 → 清理旧工具结果 → 摘要压缩。
会话持久化：每轮结束存 JSON，下个会话从这里恢复（interrupt and resume）。

参考：NamiAgent lesson-04（https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-04）
"""
import json
import os
from pathlib import Path

MAX_TOOL_CHARS = 4000          # 第 1 层：单个工具结果最多保留的字符数
KEEP_RECENT_TOOL_RESULTS = 3   # 第 2 层：清理时保留最近几条工具结果
KEEP_LAST_TURNS = 2            # 第 3 层：压缩时原样保留最近几轮 user 消息

# 程序自己的状态放在工作区之外，Agent 的文件工具碰不到
STATE_DIR = Path(os.environ.get("AGENT_STUDY_STATE_DIR", Path.home() / ".agent-study" / "day2"))
SESSION_DIR = STATE_DIR / "sessions"

PLACEHOLDER = "[旧工具结果已清理，如需要请重新调用工具]"

SUMMARY_PROMPT = """你是对话摘要器。把下面这段 Agent 的历史对话压缩成摘要，要求：
1. 保留：用户的目标、已完成的步骤、关键结论、重要的文件路径和参数、尚未解决的问题
2. 丢弃：寒暄、重复内容、工具返回的大段原文
3. 用简洁的条目写，不超过 500 字
只输出摘要本身。"""


# ---------- 第 1 层：截断工具结果（保头保尾，去中间） ----------
def truncate_tool_result(text: str, limit: int = MAX_TOOL_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n...[中间省略 {len(text) - limit} 字符]...\n{text[-half:]}"


# ---------- 第 2 层：清理旧工具结果（只改内容，不删消息，保持 tool_call 配对） ----------
def clear_old_tool_results(messages: list, keep: int = KEEP_RECENT_TOOL_RESULTS) -> None:
    tool_idx = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    for i in (tool_idx[:-keep] if keep > 0 else tool_idx):
        messages[i]["content"] = PLACEHOLDER


# ---------- 第 3 层：摘要压缩（只在 user 消息处切，避免拆散工具调用对） ----------
def split_for_compact(messages: list, keep_turns: int = KEEP_LAST_TURNS):
    """返回 (要压缩的旧消息, 原样保留的新消息)；没得压返回 None。messages[0] 约定是 system。"""
    user_idx = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(user_idx) <= keep_turns:
        return None
    cut = user_idx[-keep_turns]
    return messages[1:cut], messages[cut:]


def render_for_summary(msgs: list) -> str:
    lines = []
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = ", ".join(
                f'{c["function"]["name"]}({c["function"]["arguments"]})' for c in m["tool_calls"]
            )
            if m.get("content"):
                lines.append(f'[assistant] {m["content"]}')
            lines.append(f"[assistant 调用工具] {calls}")
        else:
            lines.append(f'[{m["role"]}] {m.get("content") or ""}')
    return "\n".join(lines)


def compact(client, model: str, messages: list) -> list:
    parts = split_for_compact(messages)
    if parts is None:
        return messages
    old, recent = parts
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": render_for_summary(old)},
        ],
    )
    summary = resp.choices[0].message.content
    return [
        messages[0],
        {"role": "user", "content": f"[以下是此前对话的摘要]\n{summary}"},
        {"role": "assistant", "content": "好的，我已了解之前的进展，继续。"},
        *recent,
    ]


# ---------- 会话持久化：save / load 就是整个 interrupt-and-resume ----------
def save_session(name: str, messages: list) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    (SESSION_DIR / f"{name}.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_session(name: str):
    path = SESSION_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
