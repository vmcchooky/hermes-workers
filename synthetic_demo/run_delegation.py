import sys
import json

sys.path.insert(0, r"D:\Hermes\hermes-agent")
from tools.terminal_tool import terminal_tool

cmd = 'codex exec "Tạo file add.py chứa hàm cộng hai số (add) và file test_add.py chứa unittest cho hàm add. Sau đó chạy python -m unittest test_add.py và kết thúc." --cd "D:/Hermes/synthetic_demo" --sandbox workspace-write < /dev/null'

res = terminal_tool(
    command=cmd,
    workdir=r"D:\Hermes\synthetic_demo",
    pty=False,
    timeout=120
)
print("TERMINAL_PARAMS: pty=False, timeout=120")
print("JSON_RESULT:", res)
