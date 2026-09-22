import subprocess
import time
import os
import signal

env = os.environ.copy()
env['PATH'] = 'C:\\Program Files\\Git\\usr\\bin;' + env.get('PATH', '')

# CREATE_NEW_PROCESS_GROUP = 512
p = subprocess.Popen(['C:\\Program Files\\Git\\usr\\bin\\bash.exe', '-c', 'eval \'bash -c "python zombie.py"\''], cwd=r'D:\Hermes\synthetic_demo', env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
time.sleep(1)
print('PID:', p.pid)
os.kill(p.pid, signal.CTRL_BREAK_EVENT)
time.sleep(1)
print("Finished killing")
