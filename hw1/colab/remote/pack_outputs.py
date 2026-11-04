"""Tar the outputs into one file. Invoked by ``run.ps1 -Fetch``.

One archive beats N ``colab download`` calls: the local side would otherwise have to know
every run directory name in advance.  ``pack_exclude`` in /content/setup.json is a list of
path fragments to leave out -- checkpoints and other large artifacts nothing local reads.
It is read from that file rather than the environment because ``colab exec`` has no way
to pass one.

RESUMABLE STATE IS SNAPSHOTTED, NOT TARRED IN PLACE.  A long run rotates its checkpoint with
``os.replace`` every few minutes.  ``tarfile.add`` stats a file for its size and then reads
it, so a rotation landing between the two produces ``Truncated tar archive detected`` locally
and a **corrupt** checkpoint -- which is precisely the file the fetch exists to protect, and
the corruption is silent because the small append-only outputs in the same archive arrive
intact.  Measured on the kissing GPU job, 2026-08-25: two fetches in a row, two unusable
checkpoints, and an hour of work lost when the VM was reclaimed.

So every ``.npz`` is copied to a scratch file first, the copy is opened as a zip to prove it
is complete, and the COPY is what goes into the archive under the original name.  A copy that
does not verify is retried; if it still does not, the file is skipped with a loud line rather
than shipped broken.  Small text outputs are tarred directly, as before.
"""

import json
import os
import shutil
import tarfile
import time
import zipfile

OUT = "/content/out"
ARCHIVE = "/content/outputs.tar.gz"
SETUP = "/content/setup.json"
SNAPDIR = "/content/.packsnap"
# `or []` matters: a hand-edited setup.json with "pack_exclude": null would otherwise
# make `keep` raise TypeError and abort the whole fetch
EXCLUDE = (json.load(open(SETUP)).get("pack_exclude") or []) if os.path.exists(SETUP) else []

if not os.path.isdir(OUT):
    raise SystemExit(f"no output directory at {OUT} -- has anything run yet?")
os.makedirs(SNAPDIR, exist_ok=True)


def keep(info):
    return None if any(part in info.name for part in EXCLUDE) else info


def total_size(path):
    if not os.path.isdir(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(root, name))
               for root, _dirs, files in os.walk(path) for name in files)


def snapshot(path, tries=4):
    """A copy of `path` proved to be a complete zip, or None."""
    dst = os.path.join(SNAPDIR, os.path.basename(path))
    for attempt in range(tries):
        try:
            shutil.copyfile(path, dst)
            with zipfile.ZipFile(dst) as z:
                if z.testzip() is None:
                    return dst
        except Exception as exc:                       # replaced under us; try again
            last = exc
        time.sleep(1.5)
    print(f"  {os.path.basename(path):<50} SKIPPED -- could not snapshot a complete copy "
          f"in {tries} attempts")
    return None


with tarfile.open(ARCHIVE, "w:gz") as tar:
    for name in sorted(os.listdir(OUT)):
        path = os.path.join(OUT, name)
        src = path
        if os.path.isfile(path) and name.endswith(".npz"):
            src = snapshot(path)
            if src is None:
                continue
        tar.add(src, arcname=name, filter=keep)
        print(f"  {name:<50} {total_size(path):>12,} bytes")

print(f"\npacked -> {ARCHIVE} ({os.path.getsize(ARCHIVE):,} bytes)")
