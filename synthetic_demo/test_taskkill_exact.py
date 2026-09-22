import subprocess
import time

script = """
eval 'bash -c "python zombie.py"'
__hermes_ec=$?
exit $__hermes_ec
"""

p = subprocess.Popen(['C:\\Program Files\\Git\\usr\\bin\\bash.exe', '-c', script], cwd=r'D:\Hermes\synthetic_demo', start_new_session=True, creationflags=subprocess.CREATE_NO_WINDOW)
time.sleep(1)
print('PID:', p.pid)
subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)])

