# agent-study

AI agent 学习笔记：课程 Q&A、最小实现、实验记录。

## Lessons

### Stage 1 / Day 1

| # | Topic | Artifacts |
|---|-------|-----------|
| 1 | 最小 Agent：tool-calling 全链路（tools JSON → chat template → tool_calls → 执行回填） | [agent.py](stage1/day1/agent.py)、[Modelfile](stage1/day1/Modelfile)（本地 GGUF 导入 Ollama）、[response.json](stage1/day1/response.json)（原始 HTTP 响应样例）（参考 [NamiAgent lesson-01](https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-01)） |

### Stage 1 / Day 2

| # | Topic | Artifacts |
|---|-------|-----------|
| 2 | 状态、上下文与持久化：截断 → 清理 → 摘要三级上下文管理 + 会话落盘恢复（interrupt and resume） | [agent.py](stage1/day2/agent.py)、[context.py](stage1/day2/context.py)（参考 [NamiAgent lesson-04](https://github.com/aa1143/NamiAgent/tree/main/lessons/lesson-04)） |

## Local model setup

```bash
# 用户态 ollama 实例，模型目录在大盘
OLLAMA_MODELS=/mnt/ai-workspace/ollama-models OLLAMA_HOST=127.0.0.1:11435 ollama serve

# 从本地 GGUF 导入（零下载）
OLLAMA_HOST=127.0.0.1:11435 ollama create qwen3.8-27b -f stage1/day1/Modelfile

# 跑第 1 课
API_KEY=ollama BASE_URL=http://127.0.0.1:11435/v1 MODEL=qwen3.8-27b .venv/bin/python stage1/day1/agent.py "..."

# 跑第 2 课（REPL，exit 退出后重进可恢复上下文）
API_KEY=ollama BASE_URL=http://127.0.0.1:11435/v1 MODEL=qwen3.8-27b .venv/bin/python stage1/day2/agent.py
```

## Repo conventions

[agent-ready/](agent-ready/) 以 git submodule 引入，提供 [AGENTS.md](agent-ready/AGENTS.md)
和可复用 skills（git-commit、weekly-report、agents-md、skill-scaffold）。
在本仓库提交请遵循 agent-ready 里的约定。
