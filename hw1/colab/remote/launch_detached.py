"""Start a training job on the Colab VM without holding the exec channel open.

Colab's free tier reclaims idle-looking VMs, and three runs of this campaign were lost
because results existed only on the VM when it went away. The obvious fix, polling and
downloading each file as it appears, does not work if the job is started with a foreground
``colab exec``: that call occupies the session until the job ends, so every later exec,
including the download, queues behind it and cannot run until it is too late.

This starts the job detached and returns immediately, so short polling calls interleave
with training and each result is copied off the VM as soon as it exists.

Usage: upload the argument vector to ``/content/job_cmd.txt`` (one argument per line, the
first being the script path), then ``colab exec -f launch_detached.py``. Re-running while
the job is alive is a no-op, so a poller may call it defensively.
"""

import subprocess
import sys
from pathlib import Path

CMD_FILE = Path("/content/job_cmd.txt")
LOG = Path("/content/job.log")
PIDFILE = Path("/content/job.pid")

if not CMD_FILE.exists():
    raise SystemExit(f"{CMD_FILE} not found -- upload the argument vector first")

argv = [line for line in CMD_FILE.read_text().splitlines() if line.strip()]
if not argv:
    raise SystemExit(f"{CMD_FILE} is empty")

if PIDFILE.exists():
    pid = PIDFILE.read_text().strip()
    # The existence of /proc/<pid> is not enough: Linux reuses pids, and a stale file
    # pointing at a recycled pid made this report "already running" after the previous
    # job had died, so a relaunch silently did nothing. Confirm it is our command.
    alive = False
    if pid.isdigit():
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
            alive = argv[0] in cmdline
        except OSError:
            alive = False
    if alive:
        print(f"job already running with pid {pid}")
        raise SystemExit(0)
    print(f"ignoring stale pid file ({pid or 'empty'})")
    PIDFILE.unlink()

handle = open(LOG, "ab", buffering=0)
process = subprocess.Popen(
    [sys.executable, "-u", *argv],
    stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    cwd="/content/proj", start_new_session=True,
)
PIDFILE.write_text(str(process.pid))
print(f"started pid {process.pid}: {' '.join(argv)}")
print(f"logging to {LOG}")
