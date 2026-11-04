import json
import os
from pathlib import Path
import subprocess
import sys
import time

jobs = json.loads(Path('/content/job_seq.json').read_text())
env = dict(os.environ, OUT_DIR='/content/out', PYTHONPATH='/content/proj')
for number, argv in enumerate(jobs, 1):
    print(f'JOB {number}/{len(jobs)}: {argv}', flush=True)
    start = time.monotonic()
    result = subprocess.run([sys.executable, '-u', *argv], cwd='/content/proj', env=env)
    print(f'EXIT {result.returncode} ELAPSED {time.monotonic() - start:.1f}s', flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
print('SEQUENCE SUCCEEDED', flush=True)