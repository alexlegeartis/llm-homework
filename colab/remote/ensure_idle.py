from pathlib import Path

pidfile = Path('/content/job.pid')
if pidfile.exists():
    pid = pidfile.read_text().strip()
    command = Path(f'/proc/{pid}/cmdline')
    if pid.isdigit() and command.exists() and b'/content/run_sequence.py' in command.read_bytes():
        raise SystemExit(f'Job {pid} is running; wait or use -StopJob before syncing or launching')
print('No active job')