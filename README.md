# agent-study

AI agent 学习笔记：课程 Q&A、最小实现、实验记录。

## Lessons

### Stage 1 / Day 1

| # | Topic | Artifacts |
|---|-------|-----------|
| 1 | 最小 Agent：tool-calling 全链路（tools JSON → chat template → tool_calls → 执行回填） | [agent.py](stage1/day1/agent.py)、[Modelfile](stage1/day1/Modelfile)（本地 GGUF 导入 Ollama）、[response.json](stage1/day1/response.json)（原始 HTTP 响应样例） |

## Local model setup

```bash
# 用户态 ollama 实例，模型目录在大盘
OLLAMA_MODELS=/mnt/ai-workspace/ollama-models OLLAMA_HOST=127.0.0.1:11435 ollama serve

# 从本地 GGUF 导入（零下载）
OLLAMA_HOST=127.0.0.1:11435 ollama create qwen3.8-27b -f stage1/day1/Modelfile

# 跑第 1 课
API_KEY=ollama BASE_URL=http://127.0.0.1:11435/v1 MODEL=qwen3.8-27b .venv/bin/python stage1/day1/agent.py "..."
```

## Repo conventions

[agent-ready/](agent-ready/) 以 git submodule 引入，提供 [AGENTS.md](agent-ready/AGENTS.md)
和可复用 skills（git-commit、weekly-report、agents-md、skill-scaffold）。
在本仓库提交请遵循 agent-ready 里的约定。
