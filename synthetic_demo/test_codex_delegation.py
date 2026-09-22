import sys
import json
import time

sys.path.insert(0, r"D:\Hermes\hermes-agent")
from tools.terminal_tool import terminal_tool

# Pin model, synthetic data, fixed deadline
cmd = 'codex exec "Calculate 2+2 and print the result" --cd "D:/Hermes/synthetic_demo" --sandbox workspace-write < /dev/null'

print(f"Executing: {cmd}")
# We'll run it with background=True so we can cancel it? No, just foreground with timeout.
res = terminal_tool(command=cmd, workdir=r"D:\Hermes\synthetic_demo", pty=False, timeout=60)
print("\nCodex Result:")
print(res)
