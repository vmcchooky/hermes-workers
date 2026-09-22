import sys
import os
import time

sys.path.insert(0, r"D:\Hermes\hermes-agent")
from tools.terminal_tool import terminal_tool

def test_pty_background():
    print("--- Running zombie via PTY Background ---")
    try:
        cmd = 'bash -c "python zombie.py"'
        result_json = terminal_tool(command=cmd, workdir=r"D:\Hermes\synthetic_demo", pty=True, background=True)
        print("Result:", result_json)
        
        import json
        res = json.loads(result_json)
        session_id = res['session_id']
        
        time.sleep(2)
        
        from tools.process_registry import process_registry
        print("Killing process:", session_id)
        process_registry.kill_process(session_id)
        print("Killed.")
        
    except Exception as e:
        print("Exception:", e)
    print("--- End ---")

if __name__ == "__main__":
    test_pty_background()
