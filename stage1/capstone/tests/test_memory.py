import memory
from memory import remember, memory_section, load_entries


def test_add_replace_remove_roundtrip():
    assert "已更新长期记忆" in remember("add", text="用户偏好简洁回复")
    assert "Error" in remember("replace", text="x", old="不存在的片段")
    assert "已更新长期记忆" in remember("replace", text="用户偏好极简回复", old="简洁回复")
    assert "已更新长期记忆" in remember("remove", old="极简回复")
    assert load_entries() == []


def test_add_requires_text():
    assert "Error" in remember("add")


def test_replace_requires_unique_match():
    remember("add", text="第一条")
    remember("add", text="第二条")
    assert "匹配了 2 条" in remember("remove", old="条")
    remember("remove", old="第一条")
    assert "已更新" in remember("remove", old="第二条")


def test_memory_has_size_limit():
    assert "Error" in remember("add", text="x" * 2001)


def test_memory_section_empty_then_filled():
    assert memory_section() == ""
    remember("add", text="项目用 pnpm 不用 npm")
    section = memory_section()
    assert "长期记忆" in section and "项目用 pnpm" in section
    memory.remember("remove", old="pnpm")  # 清理，避免影响其他用例
