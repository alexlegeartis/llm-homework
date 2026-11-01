import argparse
import hashlib
from pathlib import Path
import urllib.request

from homework_01_rag.common import load_config

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
args = parser.parse_args()
config = load_config(args.config)
settings = config["tokenizer"]
target = Path(config["config_directory"]) / settings["local_path"] / settings["file"]
target.parent.mkdir(parents=True, exist_ok=True)
if not target.is_file():
    urllib.request.urlretrieve(f"https://huggingface.co/{settings['repository']}/resolve/{settings['revision']}/{settings['file']}", target)
if hashlib.sha256(target.read_bytes()).hexdigest() != settings["sha256"]:
    raise ValueError("Generator tokenizer SHA256 mismatch")
print(f"Tokenizer ready: {target}")
