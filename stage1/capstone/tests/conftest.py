"""测试前把工作区和状态目录指向临时目录，不碰你的真实文件。"""
import os
import sys
import tempfile

WS = tempfile.mkdtemp(prefix="demoagent-ws-")
os.environ["AGENT_STUDY_WORKSPACE"] = WS
os.environ["AGENT_STUDY_STATE_DIR"] = tempfile.mkdtemp(prefix="demoagent-state-")
os.environ.setdefault("API_KEY", "test")
os.chdir(WS)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
