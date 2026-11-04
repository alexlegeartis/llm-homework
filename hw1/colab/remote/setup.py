"""Unpack the code bundle on the VM and make it runnable. Invoked by ``run.ps1 -Sync``.

Project-independent: everything variable is read from ``/content/setup.json``, which
``run.ps1`` uploads from the project's own config.  Two things a plain unzip does not do:

  * PowerShell's ``Compress-Archive`` stores ``a\\b.py`` as the entry name, and a
    backslash is a legal filename character on Linux -- so ``extractall`` would produce
    files literally named ``src\\model.py`` and no package to import.
  * The pip install is the slow part of a sync and must print as it goes, because
    ``colab exec`` times out on *silence*, not on duration.

The optional ``import_check`` is a module name imported at the end.  A broken bundle then
fails here, in the foreground, rather than five minutes into a detached job whose log
nobody is watching yet.
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile

TARGET = "/content/proj"
BUNDLE = "/content/bundle.zip"
OUT = "/content/out"

config = json.loads(open("/content/setup.json").read()) if os.path.exists("/content/setup.json") else {}
packages = config.get("pip") or []      # a JSON null must behave like an empty list
import_check = config.get("import_check")

# --- 1. unpack ---------------------------------------------------------------
shutil.rmtree(TARGET, ignore_errors=True)
with zipfile.ZipFile(BUNDLE) as archive:
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.endswith("/"):
            continue
        destination = os.path.join(TARGET, name)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with archive.open(info) as source, open(destination, "wb") as out:
            shutil.copyfileobj(source, out)
count = sum(len(files) for _root, _dirs, files in os.walk(TARGET))
print(f"unpacked {count} files into {TARGET}", flush=True)

# --- 2. dependencies ---------------------------------------------------------
if packages:
    print(f"installing {len(packages)} package(s) ...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", *packages],
        capture_output=True, text=True,
    )
    print(result.stdout[-2000:], flush=True)
    if result.returncode != 0:
        print(result.stderr[-4000:], flush=True)
        raise SystemExit(f"pip install failed with code {result.returncode}")
print("dependencies ok", flush=True)

# --- 3. report the environment ------------------------------------------------
os.makedirs(OUT, exist_ok=True)
import torch  # noqa: E402  (imported late so a missing torch is reported, not raised at top)

accelerator = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only"
print(f"python {sys.version.split()[0]} | torch {torch.__version__} | {accelerator}", flush=True)

if import_check:
    sys.path.insert(0, TARGET)
    __import__(import_check)
    print(f"import ok: {import_check}", flush=True)
