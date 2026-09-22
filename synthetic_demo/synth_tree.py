import subprocess
import time
import sys
import os

print(f"Parent PID: {os.getpid()}")
# Spawns a child that sleeps forever
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1000)"])
print(f"Child PID: {child.pid}")
sys.stdout.flush()

try:
    time.sleep(100)
except KeyboardInterrupt:
    print("Caught KeyboardInterrupt, not exiting to simulate stuck process.")
    while True:
        time.sleep(1)
