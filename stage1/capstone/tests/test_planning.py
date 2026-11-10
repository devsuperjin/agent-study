import agent
import planning
from planning import update_plan


class FakeSession:
    def __init__(self):
        self.messages = []
        self.plan = []


def _with_session():
    session = FakeSession()
    token = agent.CURRENT.set((session, None, None, print))
    return session, token


def test_update_plan_renders_steps():
    session, token = _with_session()
    try:
        out = update_plan([{"step": "读文件", "status": "completed"},
                           {"step": "改代码", "status": "in_progress"},
                           {"step": "跑测试", "status": "pending"}])
        assert "[plan] 当前计划（1/3 完成）" in out
        assert "[x] 读文件" in out and "[→] 改代码" in out and "[ ] 跑测试" in out
        assert len(session.plan) == 3
    finally:
        agent.CURRENT.reset(token)


def test_update_plan_validates_input():
    session, token = _with_session()
    try:
        assert "Error" in update_plan([])
        assert "Error" in update_plan([{"step": "x", "status": "done"}])
        assert "Error" in update_plan([{"step": "a", "status": "in_progress"},
                                       {"step": "b", "status": "in_progress"}])
    finally:
        agent.CURRENT.reset(token)


def test_old_plan_versions_get_replaced():
    session, token = _with_session()
    try:
        update_plan([{"step": "旧步骤", "status": "pending"}])
        session.messages.append({"role": "tool", "tool_call_id": "t1",
                                 "content": planning.PLAN_MARK + " 旧版全文……"})
        update_plan([{"step": "新步骤", "status": "in_progress"}])
        assert session.messages[-1]["content"] == planning.OLD_PLAN
    finally:
        agent.CURRENT.reset(token)


def test_requires_running_agent():
    import pytest
    with pytest.raises(RuntimeError):
        update_plan([{"step": "x", "status": "pending"}])
