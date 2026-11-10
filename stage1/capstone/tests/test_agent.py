import agent
from subagent import toolset
from tools import TOOLS, get_schemas


def test_import_registers_all_capability_tools():
    # 内置 + skills(第5课) + subagent(第9课) + planning(第10课) + memory(第11课)
    expected = {"list_dir", "read_file", "write_file", "run_shell", "fetch_url",
                "load_skill", "delegate", "update_plan", "submit_plan",
                "remember", "search_sessions"}
    assert expected <= set(TOOLS), f"缺工具：{expected - set(TOOLS)}"
    assert len(get_schemas()) == len(TOOLS)


def test_session_persists_and_reloads():
    s = agent.Session("t-persist")
    s.messages.append({"role": "user", "content": "记住这个数字：42"})
    s.save()
    s2 = agent.Session("t-persist")
    assert len(s2.messages) == 2
    assert s2.messages[0]["role"] == "system"          # 重载后 system 重建（记忆/技能快照）
    assert s2.messages[1]["content"] == "记住这个数字：42"


def test_session_tool_filter():
    s = agent.Session("t-filter", persist=False, tools=["read_file"])
    assert [x["function"]["name"] for x in s.schemas()] == ["read_file"]


def test_subagent_toolset():
    explore = toolset("explore")
    assert "delegate" not in explore and "remember" not in explore
    assert "read_file" in explore and "write_file" not in explore  # explore 只读
    worker = toolset("worker")
    assert "write_file" in worker and "delegate" not in worker
