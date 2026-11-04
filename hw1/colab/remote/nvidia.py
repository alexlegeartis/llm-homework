import subprocess
print(subprocess.run(['nvidia-smi'], text=True, capture_output=True).stdout)
