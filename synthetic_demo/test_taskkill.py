import subprocess
import time

p = subprocess.Popen(['C:\\Program Files\\Git\\usr\\bin\\bash.exe', '-c', 'eval \'bash -c "python zombie.py"\''])
time.sleep(1)
print('PID:', p.pid)
subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)])
