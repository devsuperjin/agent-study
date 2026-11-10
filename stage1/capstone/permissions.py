"""permissions.py —— 权限与安全边界（Day1/Day2 同一套的 capstone 收编版）

三道关卡：硬规则（人也无法放行）→ 风险分级（SAFE 放行 / CONFIRM 问人 / DENY 禁用）→ 人工确认。
capstone 新增 plan 模式（NamiAgent 第 10 课）：进入后除 submit_plan 外，
一切有副作用的操作都被代码拒绝，连问都不问——只读由代码强制，而不是靠提示词。

参考：NamiAgent lesson-03/10（https://github.com/aa1143/NamiAgent/tree/main/lessons）
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import indent

# Agent 只允许碰这个目录，默认是启动时的当前目录
WORKSPACE = Path(os.environ.get("AGENT_STUDY_WORKSPACE", os.getcwd())).resolve()
SKILLS_DIR = WORKSPACE / "skills"   # 技能目录只读，Agent 不能改自己的能力说明书


class Risk(Enum):
    SAFE = "safe"        # 只读：直接放行
    CONFIRM = "confirm"  # 有副作用：问人
    DENY = "deny"        # 永远不允许


# 工具风险登记表。没登记的工具一律按 CONFIRM 处理。
TOOL_RISK = {
    "list_dir": Risk.SAFE,
    "read_file": Risk.SAFE,
    "load_skill": Risk.SAFE,       # 读说明书，无副作用
    "delegate": Risk.SAFE,         # 子 Agent 的每个操作照样过权限检查
    "update_plan": Risk.SAFE,      # 只是记一份待办清单
    "search_sessions": Risk.SAFE,  # 只读
    "submit_plan": Risk.CONFIRM,   # 计划要你批准，确认界面展示完整计划
    "remember": Risk.CONFIRM,      # 每一条长期记忆都要你点头
    "write_file": Risk.CONFIRM,
    "run_shell": Risk.CONFIRM,
    "fetch_url": Risk.CONFIRM,
}

# 允许"本次会话一直允许"的工具。run_shell 不在里面：每条命令都要过目。
REMEMBERABLE = {"write_file"}

# 明显的灾难性命令。这是安全带，不是安全边界。
SHELL_DENY_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|~|\*)",  # rm -rf / ~ *
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\s*\{",                                    # fork bomb
    r"(curl|wget)\b.*\|\s*(sh|bash)\b",               # curl ... | sh
    r">\s*/dev/sd",
]


def resolve_in_workspace(path_str: str) -> Path | None:
    """把路径解析成绝对路径；不在工作区内返回 None。
    resolve() 会展开 .. 和符号链接，所以 ../../etc/passwd 和指向外部的软链接都会被识别。"""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = WORKSPACE / p
    p = p.resolve()
    return p if p.is_relative_to(WORKSPACE) else None


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def render_call(name: str, args: dict, max_chars: int = 400) -> str:
    """确认界面：展示将要执行的真实内容，而不是模型的自述。"""
    if name == "run_shell":
        return f"  $ {args.get('command', '')}"
    if name == "write_file":
        content = args.get("content", "")
        preview = content[:max_chars]
        if len(content) > max_chars:
            preview += f"\n...（已截断，共 {len(content)} 字符）"
        return f"  路径：{args.get('path')}\n" + indent(preview, "    ")
    if name == "submit_plan":              # 计划全文都要给人看
        return indent(args.get("plan", ""), "  ")
    if name == "remember":                 # 要记下什么，原文给人看
        old = f"\n  原来那条（包含）：{args.get('old')}" if args.get("old") else ""
        return f"  {args.get('action')}：{args.get('text', '')}{old}"
    return f"  {args}"


class PermissionManager:
    def __init__(self, ask=None):
        self.always_allowed: set[str] = set()
        self.mode = "normal"      # "plan" 时只能读，由代码强制
        # ask 可注入：ask(name, args) -> ("y" | "n" | "a", 拒绝原因)
        self.ask = ask or self._ask_terminal

    # ---------- 对外入口 ----------
    def check(self, name: str, args: dict) -> Decision:
        # 第 1 关：硬规则，人也无法放行
        reason = self._hard_limits(name, args)
        if reason:
            return Decision(False, reason)

        # 第 2 关：风险分级
        risk = TOOL_RISK.get(name, Risk.CONFIRM)
        if risk is Risk.DENY:
            return Decision(False, f"工具 {name} 被策略禁用。")
        # 计划模式：除了提交计划，有副作用的操作一律拒绝，问都不问
        if self.mode == "plan" and risk is not Risk.SAFE and name != "submit_plan":
            return Decision(False, "当前是计划模式，只能读和调查。"
                                   "想好后调用 submit_plan 提交计划，批准后才能动手。")
        if risk is Risk.SAFE or name in self.always_allowed:
            return Decision(True)

        # 第 3 关：人工确认
        return self._confirm(name, args)

    # ---------- 第 1 关 ----------
    def _hard_limits(self, name: str, args: dict) -> str | None:
        if name in ("list_dir", "read_file", "write_file"):
            path = args.get("path", ".")
            p = resolve_in_workspace(path)
            if p is None:
                return f"路径 {path!r} 在工作区 {WORKSPACE} 之外，禁止访问。"
            if name == "write_file" and p.is_relative_to(SKILLS_DIR):
                return "技能目录是只读的，Agent 不能修改自己的技能。"
        if name == "run_shell":
            cmd = args.get("command", "")
            for pat in SHELL_DENY_PATTERNS:
                if re.search(pat, cmd):
                    return f"命令命中危险模式，已被策略拦截：{cmd!r}"
        return None

    # ---------- 第 3 关 ----------
    def _confirm(self, name: str, args: dict) -> Decision:
        answer, note = self.ask(name, args)
        if answer == "a" and name in REMEMBERABLE:
            self.always_allowed.add(name)
            return Decision(True)
        if answer in ("y", "a"):
            return Decision(True)
        msg = "用户拒绝了这次操作。"
        if note:
            msg += f"原因：{note}。"
        msg += "不要重试同一操作；请换一种方式，或向用户说明你想做什么、为什么。"
        return Decision(False, msg)

    @staticmethod
    def _ask_terminal(name: str, args: dict):
        if not sys.stdin.isatty():
            # 非交互环境（管道、脚本）没有人可以确认，默认拒绝
            return "n", "当前是非交互环境，无法确认"
        print(f"\n[权限确认] Agent 想执行：{name}")
        print(render_call(name, args))
        options = "[y]允许 / [n]拒绝" + (" / [a]本次会话一直允许" if name in REMEMBERABLE else "")
        while True:
            ans = input(f"{options} > ").strip().lower()
            if ans in ("y", "n") or (ans == "a" and name in REMEMBERABLE):
                break
        note = input("拒绝原因（可选，回车跳过）> ").strip() if ans == "n" else ""
        return ans, note
