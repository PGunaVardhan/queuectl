#!/usr/bin/env python3
"""Simple demo script for queuectl"""

import subprocess
import time
import sys

def run(cmd):
    print(f"\n> {cmd}")
    result = subprocess.run(cmd, shell=True)
    time.sleep(1)
    return result.returncode == 0

print("="*50)
print("  QUEUECTL DEMO")
print("="*50)

# Clean
run("del /Q queuectl.db* 2>nul")

# Configure
print("\n📝 Configuration:")
run('queuectl config set max-retries 3')
run('queuectl config set backoff-base 2')
run('queuectl config get')

# Enqueue
print("\n📦 Enqueueing jobs:")
run('queuectl enqueue "{\\"id\\":\\"job-1\\",\\"command\\":\\"echo Hello_World\\"}"')
run('queuectl enqueue "{\\"id\\":\\"job-2\\",\\"command\\":\\"echo Job_2\\"}"')
run('queuectl enqueue "{\\"id\\":\\"job-3\\",\\"command\\":\\"ping 127.0.0.1 -n 2\\"}"')
run('queuectl enqueue "{\\"id\\":\\"fail-job\\",\\"command\\":\\"exit 1\\",\\"max_retries\\":2}"')

# Status
print("\n📊 Queue status:")
run('queuectl status')
run('queuectl list')

print("\n✅ Demo setup complete!")
print("Now run in a separate terminal: queuectl worker start --count 2")
print("Then check status with: queuectl status")
