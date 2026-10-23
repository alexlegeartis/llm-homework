from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

import snowballstemmer

from .common import read_jsonl


STEMMER = snowballstemmer.stemmer("russian")
STOPWORDS = set("а без был была были было быть в во все всего вы для до его ее если есть же за и из или их к как ко ли на но о об от по при с со так также то у что это этой этого эти этих я".split())
SYMBOLS = {"∂": " partial ", "∫": " integral ", "∮": " integral ", "Σ": " sum ", "π": " pi ", "ζ": " zeta ", "γ": " gamma ", "φ": " phi ", "ℂ": " C ", "ℝ": " R ", "∞": " infinity "}


def tokens(text):
    for symbol, name in SYMBOLS.items():
        text = text.replace(symbol, name)
    text = re.sub(r"\\(?:mathbb|mathrm|left|right|frac|tfrac|text)\b", " ", text)
    words = re.findall(r"[а-яё]+|[a-z]+|\d+", text.lower().replace("ё", "е"))
    return [STEMMER.stemWord(word) if re.fullmatch(r"[а-я]+", word) else word for word in words if word not in STOPWORDS and (len(word) > 1 or word.isdigit())]


def build(corpus, output, config):
    blocks = read_jsonl(corpus)
    if not blocks:
        raise ValueError("The corpus is empty")
    identifiers = set()
    postings = defaultdict(list)
    lengths = []
    for i, block in enumerate(blocks):
        if not all(key in block for key in ["block_id", "page", "section", "text"]):
            raise ValueError(f"Invalid corpus block {i}")
        if block["block_id"] in identifiers or not isinstance(block["page"], int) or block["page"] < 1:
            raise ValueError(f"Invalid block ID or page: {block['block_id']}")
        identifiers.add(block["block_id"])
        counts = Counter(tokens(block["section"] + " " + block["text"]))
        lengths.append(sum(counts.values()))
        for token, frequency in counts.items():
            postings[token].append([i, frequency])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    index = {"version": 1, "blocks": blocks, "lengths": lengths, "postings": postings, "k1": config["retrieval"]["k1"], "b": config["retrieval"]["b"], "corpus_sha256": hashlib.sha256(Path(corpus).read_bytes()).hexdigest()}
    (output / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if config["retrieval"].get("dense"):
        from .embeddings import Encoder
        import numpy as np
        model = Path(config["config_directory"]) / config["embedding"]["local_path"]
        if not (model / "model.onnx").is_file():
            raise ValueError("Run prepare_models.py before building the index")
        shutil.copytree(model, output / "encoder", dirs_exist_ok=True)
        encoder = Encoder(output / "encoder")
        vectors = encoder.encode([block["text"] for block in blocks], "passage: ")
        np.save(output / "vectors.npy", vectors)
    return index


class Index:
    def __init__(self, path):
        data = json.loads((Path(path) / "index.json").read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported index version")
        self.blocks = data["blocks"]
        self.postings = data["postings"]
        self.lengths = data["lengths"]
        self.average = sum(self.lengths) / len(self.lengths)
        self.k1, self.b = data["k1"], data["b"]
        self.directory = Path(path)
        self.encoder = None
        self.vectors = None

    def load_encoder(self):
        import numpy as np
        if self.encoder is None:
            from .embeddings import Encoder
            self.encoder = Encoder(self.directory / "encoder")
            self.vectors = np.load(self.directory / "vectors.npy")

    def dense_search(self, text, limit):
        self.load_encoder()
        query = self.encoder.encode([text], "query: ")[0]
        scores = self.vectors @ query
        return sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:limit]

    def search(self, text, limit):
        scores = defaultdict(float)
        size = len(self.blocks)
        for token, weight in Counter(tokens(text)).items():
            entries = self.postings.get(token, [])
            idf = math.log(1 + (size - len(entries) + 0.5) / (len(entries) + 0.5))
            for i, frequency in entries:
                norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.average)
                scores[i] += min(weight, 2) * idf * frequency * (self.k1 + 1) / (frequency + norm)
        return sorted(scores, key=lambda i: (-scores[i], i))[:limit]

    def retrieve(self, question, settings, mode, rewritten=None):
        if mode == "no_context":
            return []
        query = question["question"]
        options = [option["text"] for option in question["options"]]
        if mode == "baseline":
            ranked = self.search(query + " " + " ".join(options), settings["candidate_k"])
        else:
            text = rewritten or query + " " + " ".join(options)
            rankings = [self.search(text, settings["candidate_k"])]
            if settings["dense"]:
                rankings.append(self.dense_search(text, settings["candidate_k"]))
            scores = defaultdict(float)
            for ranking in rankings:
                for rank, i in enumerate(ranking, 1):
                    scores[i] += 1 / (60 + rank)
            ranked = sorted(scores, key=lambda i: (-scores[i], i))
        return [self.blocks[i] for i in ranked[:settings["top_k"]]]
