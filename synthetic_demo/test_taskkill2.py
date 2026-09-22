import subprocess
import time
import os

env = os.environ.copy()
env['PATH'] = 'C:\\Program Files\\Git\\usr\\bin;' + env.get('PATH', '')

p = subprocess.Popen(['C:\\Program Files\\Git\\usr\\bin\\bash.exe', '-c', 'eval \'bash -c "python zombie.py"\''], cwd=r'D:\Hermes\synthetic_demo', env=env)
time.sleep(1)
print('PID:', p.pid)
subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)])
