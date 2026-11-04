from pathlib import Path
pidfile = Path('/content/job.pid')
alive = False
if pidfile.exists():
    pid = pidfile.read_text().strip()
    command = Path(f'/proc/{pid}/cmdline')
    alive = pid.isdigit() and command.exists() and b'/content/run_sequence.py' in command.read_bytes()
print(f'JOB_ALIVE {alive}')
out = Path('/content/out')
status = out / 'status.json'
if status.exists():
    print('STATUS', status.read_text())
for path in sorted(out.rglob('*')):
    if path.is_file() and '.parts' not in path.parts:
        print('FILE', path.relative_to(out).as_posix(), path.stat().st_size)
for trace in sorted(out.glob("*/.parts/*/experiments/*/trace.jsonl")):
    lines = trace.read_text().splitlines()
    print("PROGRESS", trace.relative_to(out), len(lines), "answers")
    runlog = trace.parents[2] / "run.log"
    if runlog.exists():
        print("\n".join(runlog.read_text(errors="replace").splitlines()[-2:]))
log = Path('/content/job.log')
if log.exists():
    print('\n'.join(log.read_text(errors='replace').splitlines()[-20:]))