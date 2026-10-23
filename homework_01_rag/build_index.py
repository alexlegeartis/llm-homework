import argparse
import json
from pathlib import Path
import time

import psutil

from .common import load_config
from .retrieval import build


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    data = build(args.corpus, args.output, load_config(args.config))
    memory = psutil.Process().memory_info()
    metrics = {"blocks": len(data["blocks"]), "elapsed_seconds": time.perf_counter() - start, "peak_ram_bytes": getattr(memory, "peak_wset", memory.rss), "index_bytes": sum(p.stat().st_size for p in Path(args.output).rglob("*") if p.is_file()), "corpus_sha256": data["corpus_sha256"]}
    (Path(args.output) / "build_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
