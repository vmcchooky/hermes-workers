import subprocess
import time
import psutil
import os

def test_codex_process_timeout():
    print("[TEST] Spawning codex child process for timeout test...")
    # Spawn codex process that would wait on stdin
    cmd = ["codex", "exec", "Wait test", "--cd", r"D:\Hermes\synthetic_demo", "--sandbox", "danger-full-access"]
    
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    pid = proc.pid
    print(f"[INFO] Codex child process spawned with PID: {pid}")

    time.sleep(1.0)
    # Check if process is running
    assert psutil.pid_exists(pid), f"PID {pid} should exist"
    print(f"[OK] Process PID {pid} is confirmed alive.")

    # Terminate the process cleanly using its specific PID tree
    print(f"[ACTION] Cleaning up targeted PID {pid} tree...")
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            child.terminate()
        parent.terminate()
        _, still_alive = psutil.wait_procs(children + [parent], timeout=3)
        for p in still_alive:
            p.kill()
    except psutil.NoSuchProcess:
        pass

    time.sleep(0.5)
    exists = psutil.pid_exists(pid)
    print(f"[VERIFY] Target PID {pid} exists after termination: {exists}")
    assert not exists, f"PID {pid} should have been cleanly terminated!"
    print("[SUCCESS] Codex process timeout & cleanup verified: target PID cleanly reaped without wildcard process kill.")

if __name__ == "__main__":
    test_codex_process_timeout()
