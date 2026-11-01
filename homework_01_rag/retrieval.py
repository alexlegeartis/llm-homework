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

LATEX = {"partial": "∂", "int": "∫", "oint": "∮", "sum": "Σ", "pi": "π", "zeta": "ζ", "gamma": "γ", "varphi": "φ", "phi": "φ", "infty": "∞", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠", "sin": "sin", "cos": "cos", "exp": "exp", "equiv": "≡"}


def math_query(text):
    text = re.sub(r"\\(?:tfrac|dfrac|frac)\s*(?:\{([^{}]*)\}|([^\s{}]))\s*(?:\{([^{}]*)\}|([^\s{}]))", lambda m: "(" + (m[1] or m[2]) + ")/(" + (m[3] or m[4]) + ")", text)
    text = re.sub(r"\\(?:bar|overline)\s*(?:\{([^}]+)\}|([a-z]))", lambda m: " bar(" + (m[1] or m[2]) + ") ", text)
    text = text.replace(r"\mathbb{C}", "ℂ").replace(r"\mathbb C", "ℂ").replace(r"\mathbb{R}", "ℝ")
    return re.sub(r"\\([A-Za-z]+)", lambda m: LATEX.get(m[1], m[0]), text).replace("$", "")


def expand_queries(question):
    text = math_query(question["question"] + " " + " ".join(option["text"] for option in question["options"])).lower()
    rules = [
        (r"bar\(z\)|сопряж[а-я]* переменн", "∂f ∂bar(z)"),
        (r"коши[— –-]*риман|комплексн[а-я]* дифференц", "необходимо достаточно вещественном смысле"),
        (r"вычисл[а-я]*.*(?:интеграл|∫|∮)|(?:производн[а-я]*.*(?:интеграл|∫|∮))", "интегральная формула Коши для производных"),
        (r"интеграл[а-я ]{0,8}коши|φ|непрерывн[а-я]* на (?:ней|кривой)", "Интеграл Коши бесконечно дифференцируемую"),
        (r"e\^|экспонент", "экспонента показательная функция производная"),
        (r"первообразн", "первообразная интеграл замкнутая кривая локальное глобальное существование"),
        (r"гармонич", "сопряженные гармонические Коши Римана"),
        (r"единственност|предельн[а-я]* точк|нул(?:ей|и|я)", "теорема единственности голоморфные функции множество предельная точка"),
        (r"всех порядк|бесконечн[а-я]* дифференц", "Голоморфная в области функция бесконечно дифференцируемой n!"),
        (r"\bsin\b|\bcos\b", "синус косинус sin cos"),
        (r"тейлор|степенн[а-я]* ряд|коэффициент|σ", "коэффициенты c_n n!"),
    ]
    queries = [query for pattern, query in rules if re.search(pattern, text)]
    if re.search(r"цел(?:ая|ой|ую|ые)", text) and re.search(r"огранич|≤|оценк", text):
        queries.append("теорема Лиувилля целая ограниченная функция")
    return queries or None


def tokens(text):
    text = math_query(text)
    for symbol, name in SYMBOLS.items():
        text = text.replace(symbol, name)
    text = re.sub(r"\\(?:mathbb|mathrm|left|right|frac|tfrac|text)\b", " ", text)
    words = re.findall(r"[а-яё]+|[a-z]+|\d+", text.lower().replace("ё", "е"))
    return [STEMMER.stemWord(word) if re.fullmatch(r"[а-я]+", word) else word for word in words if word not in STOPWORDS]


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
    if config.get("tokenizer"):
        source = Path(config["config_directory"]) / config["tokenizer"]["local_path"] / config["tokenizer"]["file"]
        shutil.copyfile(source, output / "generation_tokenizer.json")
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
        self.formula_blocks = {}
        for i, block in enumerate(self.blocks):
            for reference in re.findall(r"\(\d+\.\d+\)", block["text"]):
                self.formula_blocks.setdefault(reference, i)

    def load_tokenizer(self):
        from tokenizers import Tokenizer
        return Tokenizer.from_file(str(self.directory / "generation_tokenizer.json"))

    def search(self, text, limit, number_weight=1.0):
        scores = defaultdict(float)
        size = len(self.blocks)
        for token, weight in Counter(tokens(text)).items():
            entries = self.postings.get(token, [])
            idf = math.log(1 + (size - len(entries) + 0.5) / (len(entries) + 0.5))
            for i, frequency in entries:
                norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.average)
                numeric = number_weight if token.isdigit() else 1.0
                scores[i] += numeric * min(weight, 2) * idf * frequency * (self.k1 + 1) / (frequency + norm)
        return sorted(scores, key=lambda i: (-scores[i], i))[:limit]

    def retrieve(self, question, settings, mode, queries=None):
        if mode == "no_context":
            return []
        query = question["question"]
        options = [option["text"] for option in question["options"]]
        text = query + " " + " ".join(options)
        limit = settings["candidate_k"]
        if mode == "baseline":
            ranked = self.search(text, limit)
            seeds = ranked[:settings["top_k"]]
        else:
            def search(value):
                ranking = self.search(value, 2 * limit, 0.15)
                return [i for i in ranking if self.blocks[i].get("section") != "Содержание"][:limit]

            anchors = [ranking[0] for value in queries or [] if (ranking := search(value))]
            ranked = search(text + " " + " ".join(queries or []))
            seeds = list(dict.fromkeys(anchors + ranked))[:settings["top_k"]]
        if mode != "final" or not settings.get("neighbors"):
            return [self.blocks[i] for i in seeds]
        expanded = []
        for i in seeds:
            related = [i]
            block = self.blocks[i]
            for reference in re.findall(r"\(\d+\.\d+\)", block["text"]):
                source = getattr(self, "formula_blocks", {}).get(reference)
                if source is not None and source != i and source not in related:
                    related.append(source)
            for j in range(i + 1, min(i + 3, len(self.blocks))):
                following = self.blocks[j]
                if following["section"] != block["section"] or following["page"] - block["page"] > 1 or re.match(r"^(?:Теорема|Следствие|Лемма|Определение|Замечание|Доказательство)\b", following["text"]):
                    break
                related.append(j)
            for j in related:
                if j not in expanded:
                    expanded.append(j)
        return [self.blocks[i] for i in expanded]
