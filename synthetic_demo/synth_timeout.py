import sys, time, subprocess
print("Spawning child...")
proc = subprocess.Popen([sys.executable, "-c", "import time; print('Child running'); time.sleep(100)"])
print(f"Child PID: {proc.pid}")
time.sleep(100)
