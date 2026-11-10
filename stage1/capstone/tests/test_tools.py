from pathlib import Path

from tools import execute, list_dir


def test_execute_unknown_tool():
    out = execute("no_such_tool", {})
    assert "不存在工具" in out and "list_dir" in out  # 报错里告诉模型有哪些可用


def test_execute_never_raises():
    out = execute("read_file", {})  # 缺参数 → TypeError，也要变成字符串喂回模型
    assert out.startswith("Error:")


def test_execute_truncates_long_output():
    Path("big.txt").write_text("x" * 20000, encoding="utf-8")
    out = execute("read_file", {"path": "big.txt"})
    assert len(out) < 9000 and "已截断" in out


def test_list_dir_marks_directories():
    Path("sub").mkdir()
    Path("file.txt").write_text("hi", encoding="utf-8")
    out = list_dir(".")
    assert "sub/" in out and "file.txt" in out
