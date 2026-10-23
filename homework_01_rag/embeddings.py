from pathlib import Path
import json
import urllib.request

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


def download_model(settings, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for remote, local in [(settings["file"], "model.onnx"), ("tokenizer.json", "tokenizer.json")]:
        path = destination / local
        if not path.exists():
            url = f"https://huggingface.co/{settings['repository']}/resolve/{settings['revision']}/{remote}"
            partial = path.with_suffix(path.suffix + ".part")
            urllib.request.urlretrieve(url, partial)
            partial.replace(path)
    (destination / "model_info.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")


class Encoder:
    def __init__(self, directory):
        directory = Path(directory)
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])

    def encode(self, texts, prefix):
        vectors = []
        for start in range(0, len(texts), 4):
            encoded = self.tokenizer.encode_batch([prefix + text for text in texts[start:start + 4]])
            values = {"input_ids": np.array([item.ids for item in encoded], dtype=np.int64), "attention_mask": np.array([item.attention_mask for item in encoded], dtype=np.int64)}
            inputs = {item.name: values.get(item.name, np.zeros_like(values["input_ids"])) for item in self.session.get_inputs()}
            states = self.session.run(None, inputs)[0]
            mask = values["attention_mask"][..., None]
            pooled = (states * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
            vectors.append(pooled.astype(np.float32))
        return np.concatenate(vectors)
