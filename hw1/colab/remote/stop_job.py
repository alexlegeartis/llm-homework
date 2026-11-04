import os
from pathlib import Path
import signal
import time

pidfile = Path('/content/job.pid')
if not pidfile.exists():
    raise SystemExit('No job')
pid = pidfile.read_text().strip()
command = Path(f'/proc/{pid}/cmdline')
if not pid.isdigit() or not command.exists() or not command.read_bytes():
    pidfile.unlink()
    raise SystemExit('Job already finished')
if b'/content/run_sequence.py' not in command.read_bytes() or os.getpgid(int(pid)) != int(pid):
    raise SystemExit('PID is not an owned detached job; refusing to stop it')
os.killpg(int(pid), signal.SIGTERM)
for attempt in range(20):
    if not command.exists() or not command.read_bytes():
        break
    time.sleep(0.5)
else:
    os.killpg(int(pid), signal.SIGKILL)
pidfile.unlink(missing_ok=True)
print('Job stopped')