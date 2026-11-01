import argparse
from fnmatch import fnmatch
import json
import os
from pathlib import Path
import zipfile


parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
config = json.loads(args.project.read_text(encoding="utf-8-sig"))
root = (args.project.resolve().parent / config["bundle"]).resolve()
excluded = config.get("exclude", []) + [".git", "__pycache__", ".ipynb_checkpoints"]


def skip(name):
    return any(fnmatch(name, pattern) for pattern in excluded)


args.output.parent.mkdir(parents=True, exist_ok=True)
count = 0
with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if not skip(name))
        for name in sorted(files):
            if skip(name):
                continue
            path = Path(current) / name
            if path.is_symlink():
                continue
            archive.write(path, path.relative_to(root).as_posix())
            count += 1
print(f"Bundled {count} files: {args.output.stat().st_size:,} bytes")
