import sys
import os
import psutil
import time
import json
import re

sys.path.insert(0, r"D:\Hermes\hermes-agent")
from tools.terminal_tool import terminal_tool

print("=== EXIT 0 ===")
res = terminal_tool("python synth_exit0.py", workdir=r"D:\Hermes\synthetic_demo", pty=False)
print("Result:", res)

print("\n=== EXIT 1 ===")
res = terminal_tool("python synth_exit1.py", workdir=r"D:\Hermes\synthetic_demo", pty=False)
print("Result:", res)

print("\n=== TIMEOUT WITH CHILD ===")
import threading
def run_timeout():
    try:
        res = terminal_tool("python synth_tree.py", workdir=r"D:\Hermes\synthetic_demo", pty=False, timeout=3)
        print("\nTimeout Result:", res)
        # Parse output for PID
        out = json.loads(res).get("output", "")
        m_parent = re.search(r"Parent PID: (\d+)", out)
        m_child = re.search(r"Child PID: (\d+)", out)
        if m_parent and m_child:
            print(f"\nExtracted Parent: {m_parent.group(1)}, Child: {m_child.group(1)}")
            
            p_alive = psutil.pid_exists(int(m_parent.group(1)))
            c_alive = psutil.pid_exists(int(m_child.group(1)))
            print(f"Parent alive? {p_alive}")
            print(f"Child alive? {c_alive}")
            if not p_alive and not c_alive:
                print("SUCCESS: Both processes cleaned up.")
            else:
                print("FAILED: Leak detected.")
    except Exception as e:
        print("Exception:", e)

run_timeout()
