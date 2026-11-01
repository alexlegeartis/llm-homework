import platform,subprocess,sys
from pathlib import Path
print("PYTHON",sys.version.split()[0])
print("LIBC",platform.libc_ver())
print(Path("/etc/os-release").read_text())
result=subprocess.run(["nvcc","--version"],capture_output=True,text=True)
print(result.stdout or result.stderr)