import subprocess
import sys
import time

def test_process_timeout_and_cancel():
    print("[TEST] Spawning long-running worker child process...")
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    start_time = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    timeout_seconds = 2.0
    timed_out = False
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        elapsed = time.time() - start_time
        print(f"[OK] Caught TimeoutExpired after {elapsed:.2f}s (expected ~{timeout_seconds}s)")
        print("[ACTION] Terminating child process...")
        proc.kill()
        proc.wait()
        print(f"[OK] Child process terminated cleanly with returncode: {proc.returncode}")

    assert timed_out, "Process should have timed out"
    assert proc.poll() is not None, "Process should not be running after kill"
    print("[SUCCESS] Timeout and cancellation verified: no runaway process leaked.")

if __name__ == "__main__":
    test_process_timeout_and_cancel()
