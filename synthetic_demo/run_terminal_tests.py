import sys
import os

# Add Hermes to sys.path
sys.path.insert(0, r"D:\Hermes\hermes-agent")

from tools.terminal_tool import terminal
import asyncio

async def test_terminal(command, pty=False, timeout=10):
    print(f"--- Running: {command} (pty={pty}) ---")
    result = await terminal(command=command, workdir=r"D:\Hermes\synthetic_demo", pty=pty, timeout=timeout)
    print("Result:", result)
    print("--- End ---")

async def main():
    await test_terminal("python synth_exit0.py", pty=False)
    await test_terminal("python synth_exit1.py", pty=False)
    await test_terminal("python synth_exit0.py", pty=True)
    await test_terminal("python synth_exit1.py", pty=True)
    
    # Timeout tests
    await test_terminal("python synth_timeout.py", pty=False, timeout=3)
    await test_terminal("python synth_timeout.py", pty=True, timeout=3)

if __name__ == "__main__":
    asyncio.run(main())
