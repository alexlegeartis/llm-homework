import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"{path}:{number}: {error}") from error
    return records


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    runtime_path = path.parent / config.get("runtime", "runtime.json")
    config["runtime_settings"] = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    config["config_directory"] = str(path.parent)
    return config


def peak_ram_bytes():
    import psutil
    memory = psutil.Process().memory_info()
    if hasattr(memory, "peak_wset"):
        return memory.peak_wset
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
