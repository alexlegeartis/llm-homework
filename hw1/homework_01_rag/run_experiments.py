import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys

import psutil

from .common import peak_ram_bytes, load_config, read_jsonl
from .evaluate import evaluate
from .predict import predict
from .retrieval import Index


VARIANTS = ["no_context", "baseline", "final", "without_neighbors", "without_expansion"]
FIELDS = ["name", "answer_accuracy", "Q", "mean_input_tokens", "mean_output_tokens", "mean_llm_calls", "mean_cost", "median_latency_ms"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--names", nargs="+", choices=VARIANTS, default=VARIANTS)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    output = Path(args.output_dir).resolve()
    runs = output / "experiments"
    runs.mkdir(parents=True, exist_ok=True)
    base = load_config(args.config)
    index = Index(args.index)
    questions, gold = read_jsonl(args.questions), read_jsonl(args.gold)
    for name in ([] if args.summarize_only else args.names):
        folder = runs / name
        folder.mkdir(exist_ok=True)
        config = copy.deepcopy(base)
        config["mode"] = name if name in {"no_context", "baseline"} else "final"
        if name in {"no_context", "baseline"}:
            config["retrieval"]["query_expansion"] = False
            config["retrieval"]["neighbors"] = False
            config["retrieval"]["top_k"] = 3
        if name == "without_expansion":
            config["retrieval"]["query_expansion"] = False
        if name == "without_neighbors":
            config["retrieval"]["neighbors"] = False
        portable = copy.deepcopy({key: value for key, value in config.items() if key not in {"runtime_settings", "config_directory"}})
        portable["runtime"] = "../../runtime.json"
        if "tokenizer" in portable:
            portable["tokenizer"]["local_path"] = "../../.cache/qwen-tokenizer"
        (folder / "config.json").write_text(json.dumps(portable, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Starting {name}", file=sys.stderr, flush=True)
        submission = os.environ.get("SUBMISSION_ID", "")
        os.environ["SUBMISSION_ID"] = submission + "-" + name
        try:
            if predict(index, questions, folder / "answers.jsonl", folder / "trace.jsonl", config):
                raise RuntimeError(f"Prediction failed in {name}; inspect trace.jsonl")
        finally:
            os.environ["SUBMISSION_ID"] = submission
    baseline_trace = runs / "baseline" / "trace.jsonl"
    reference = None
    if baseline_trace.exists():
        traces = read_jsonl(baseline_trace)
        reference = sum(t["input_tokens"] + 4 * t["output_tokens"] + 256 * t["llm_calls"] for t in traces) / len(traces)
    results = []
    for name in VARIANTS:
        folder = runs / name
        if not (folder / "answers.jsonl").exists():
            continue
        metrics = evaluate(questions, gold, read_jsonl(folder / "answers.jsonl"), read_jsonl(folder / "trace.jsonl"), [b["block_id"] for b in index.blocks], name == "no_context", reference)
        (folder / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"name": name, **{key: metrics[key] for key in FIELDS if key != "name"}})
    with (output / "experiments.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    if (runs / "final" / "answers.jsonl").exists():
        shutil.copyfile(runs / "final" / "answers.jsonl", output / "dev_answers.jsonl")
        shutil.copyfile(runs / "final" / "trace.jsonl", output / "dev_trace.jsonl")
    metadata = {"platform": platform.platform(), "processor": platform.processor(), "logical_cpus": psutil.cpu_count(), "physical_cpus": psutil.cpu_count(logical=False), "total_ram_bytes": psutil.virtual_memory().total, "peak_predictor_ram_bytes": peak_ram_bytes(), "python": platform.python_version(), "baseline_reference_cost": reference, "runtime_sha256": hashlib.sha256(json.dumps(base["runtime_settings"], sort_keys=True).encode()).hexdigest()}
    if not args.summarize_only:
        (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
