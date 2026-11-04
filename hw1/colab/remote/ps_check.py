"""List surviving job processes and the current output directories.

Used after `stop_job.py` to confirm the VM really is idle before launching a new
sequence: `launch_detached.py` only knows about the pid file, and a job started while
another is still alive gives two processes writing into /content/out at once.
"""

import os
import subprocess
from pathlib import Path

found = subprocess.run(
    ["bash", "-lc", "pgrep -af 'python.*(run_sequence|/content/proj)' || echo NONE"],
    capture_output=True, text=True,
).stdout.strip()
print("PROCESSES:", found)

root = Path("/content/out")
if not root.exists():
    raise SystemExit("no /content/out")

for entry in sorted(root.iterdir()):
    size = sum(os.path.getsize(os.path.join(r, f))
               for r, _d, files in os.walk(entry) for f in files) if entry.is_dir() \
        else os.path.getsize(entry)
    print(f"DIR {entry.name} bytes={size}")
