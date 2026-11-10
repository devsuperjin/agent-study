from permissions import PermissionManager


def _failing_ask(name, args):
    raise AssertionError(f"不应走到人工确认：{name}")


def test_safe_tool_passes_without_asking():
    pm = PermissionManager(ask=_failing_ask)
    assert pm.check("read_file", {"path": "notes.txt"}).allowed


def test_write_needs_confirmation():
    assert PermissionManager(ask=lambda n, a: ("y", "")).check(
        "write_file", {"path": "a.txt", "content": "hi"}).allowed
    d = PermissionManager(ask=lambda n, a: ("n", "先不动这个文件")).check(
        "write_file", {"path": "a.txt", "content": "hi"})
    assert not d.allowed and "先不动这个文件" in d.reason


def test_always_allowed_remembers_choice():
    pm = PermissionManager(ask=lambda n, a: ("a", ""))
    assert pm.check("write_file", {"path": "a.txt", "content": "x"}).allowed
    pm.ask = _failing_ask  # 第二次不再问
    assert pm.check("write_file", {"path": "b.txt", "content": "x"}).allowed


def test_run_shell_confirms_every_time():
    pm = PermissionManager(ask=lambda n, a: ("a", ""))
    assert pm.check("run_shell", {"command": "ls"}).allowed
    asked = []
    pm.ask = lambda n, a: asked.append(n) or ("n", "")
    assert not pm.check("run_shell", {"command": "ls"}).allowed
    assert asked == ["run_shell"]  # run_shell 不进 always_allowed：每条命令都要重新过目


def test_hard_limit_dangerous_shell():
    pm = PermissionManager(ask=_failing_ask)
    d = pm.check("run_shell", {"command": "sudo rm -rf /"})
    assert not d.allowed


def test_hard_limit_outside_workspace():
    pm = PermissionManager(ask=_failing_ask)
    assert not pm.check("write_file", {"path": "../evil.txt", "content": "x"}).allowed


def test_plan_mode_blocks_write_without_asking():
    pm = PermissionManager(ask=_failing_ask)
    pm.mode = "plan"
    d = pm.check("write_file", {"path": "a.txt", "content": "x"})
    assert not d.allowed and "计划模式" in d.reason
    assert pm.check("read_file", {"path": "a.txt"}).allowed          # 只读放行
    # submit_plan 是 CONFIRM：确认界面就是计划审批本身，批准即放行
    pm2 = PermissionManager(ask=lambda n, a: ("y", ""))
    pm2.mode = "plan"
    assert pm2.check("submit_plan", {"plan": "1. ..."}).allowed
