from pathlib import Path

pidfile = Path('/content/job.pid')
if pidfile.exists():
    pid = pidfile.read_text().strip()
    command = Path(f'/proc/{pid}/cmdline')
    if pid.isdigit() and command.exists() and b'/content/run_sequence.py' in command.read_bytes():
        raise SystemExit(f'Job {pid} is still running; stop or finish it before launching another')
    pidfile.unlink()
log = Path('/content/job.log')
log.write_text('')
print('Cleared stale job state')