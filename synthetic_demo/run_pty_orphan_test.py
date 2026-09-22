import sys
import os

sys.path.insert(0, r"D:\Hermes\hermes-agent")
from tools.terminal_tool import terminal_tool

def test_terminal():
    print("--- Running zombie via PTY ---")
    try:
        # We run it via bash to simulate what Hermes does
        # Hermes uses bash for terminal commands
        cmd = 'bash -c "python zombie.py"'
        result = terminal_tool(command=cmd, workdir=r"D:\Hermes\synthetic_demo", pty=True, timeout=2)
        print("Result:", result)
    except Exception as e:
        print("Exception:", e)
    print("--- End ---")

if __name__ == "__main__":
    test_terminal()
