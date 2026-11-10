"""tools.py —— 工具注册表（装饰器注册，导入即生效）+ 内置工具

注册表是全部扩展点的地基：skills / 计划 / 记忆 / 子 Agent 都是在各自模块里
用同一个 @tool 装饰器把新工具挂进来，agent.py 不需要认识它们。

参考：NamiAgent lesson-02（https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-02）
"""
import subprocess
import urllib.request

from permissions import WORKSPACE, resolve_in_workspace

MAX_OUTPUT = 8000
TOOLS = {}


def tool(name, description, parameters):
    def decorator(func):
        TOOLS[name] = {
            "schema": {"type": "function", "function": {
                "name": name, "description": description, "parameters": parameters}},
            "func": func,
        }
        return func
    return decorator


def get_schemas():
    return [t["schema"] for t in TOOLS.values()]


def _params(**props):
    return {"type": "object",
            "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
            "required": list(props)}


@tool("list_dir", "列出工作区内某个目录下的文件和子目录。", _params(path="目录路径，工作区根目录写 ."))
def list_dir(path="."):
    p = resolve_in_workspace(path)
    if p is None:                      # 双保险：即使绕过了权限检查，这里还会拦
        return "[错误] 路径在工作区之外"
    return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())) or "(空目录)"


@tool("read_file", "读取一个文本文件的内容。", _params(path="文件路径"))
def read_file(path):
    p = resolve_in_workspace(path)
    if p is None:
        return "[错误] 路径在工作区之外"
    return p.read_text(encoding="utf-8")


@tool("write_file", "把内容写入文件，已存在则覆盖。", _params(path="文件路径", content="完整内容"))
def write_file(path, content):
    p = resolve_in_workspace(path)
    if p is None:
        return "[错误] 路径在工作区之外"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {p.relative_to(WORKSPACE)}（{len(content)} 字符）"


@tool("run_shell", "在工作区执行一条 shell 命令。", _params(command="要执行的命令"))
def run_shell(command, timeout=30):
    try:
        p = subprocess.run(command, shell=True, cwd=WORKSPACE,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"[超时] 命令执行超过 {timeout} 秒，已终止。"
    return f"[exit {p.returncode}]\n{p.stdout}{p.stderr}"


@tool("fetch_url", "抓取网页文本，url 以 http/https 开头。", _params(url="完整的 URL"))
def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "demo-agent"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def execute(name, args):
    """执行工具，永远返回字符串，永远不抛异常——出错也作为文本喂回模型，让它自己修正。"""
    if name not in TOOLS:
        return f"Error: 不存在工具 '{name}'，可用工具：{', '.join(TOOLS)}"
    try:
        result = str(TOOLS[name]["func"](**args))
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
    if len(result) > MAX_OUTPUT:
        result = result[:MAX_OUTPUT] + f"\n...（已截断，共 {len(result)} 字符）"
    return result
