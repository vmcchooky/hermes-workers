import sys
import os

# Add Hermes to sys.path
sys.path.insert(0, r"D:\Hermes\hermes-agent")

from tools.terminal_tool import terminal_tool

def test_terminal(command, pty=False, timeout=10):
    print(f"--- Running: {command} (pty={pty}) ---")
    try:
        result = terminal_tool(command=command, workdir=r"D:\Hermes\synthetic_demo", pty=pty, timeout=timeout)
        print("Result:", result)
    except Exception as e:
        print("Exception:", e)
    print("--- End ---")

def main():
    test_terminal("python synth_exit0.py", pty=False)
    test_terminal("python synth_exit1.py", pty=False)
    test_terminal("python synth_timeout.py", pty=False, timeout=3)
    test_terminal("python synth_timeout.py", pty=True, timeout=3)

if __name__ == "__main__":
    main()
