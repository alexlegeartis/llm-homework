import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from .common import ROOT, write_jsonl
from .pdf_text import extract_corpus


PDF_SHA256 = "629f4b668ff43abf2a6e621aefd0f50e165ce8e88c52c05769149e1267d033ec"
CATEGORIES = {"условия": "conditions", "сопоставление": "comparison", "применение": "calculation", "недостаточность данных": "insufficient"}


def source(blocks, page, phrase):
    matches = [block["block_id"] for block in blocks if block["page"] == page and phrase in block["text"]]
    if len(matches) != 1:
        raise ValueError(f"Expected one source for page {page}, {phrase!r}; found {matches}")
    return matches[0]


def dev_dataset(markdown, blocks):
    selectors = {
        1: [[(11, "Теорема 2.1.")]],
        2: [[(12, "В этих терминах")]],
        3: [[(11, "Теорема 2.1."), (13, "Определение 2.3.")]],
        4: [[(31, "Замечание 4.1."), (28, "= 2πi")], [(26, "Теорема 4.1."), (31, "Замечание 4.1."), (28, "= 2πi")]],
        5: [[(30, "Теорема 4.4.")]],
        6: [[(31, "Теорема 5.1"), (32, "является голоморфной в"), (33, "Следствие 5.1.")], [(33, "Следствие 5.1.")]],
        7: [[(20, "определяет"), (34, "Теорема 5.3.")]],
        8: [[(35, "Теорема 5.4")]],
        9: [[(11, "Теорема 2.1."), (13, "Система уравнений"), (34, "Теорема 5.3.")], [(11, "Теорема 2.1."), (13, "Определение 2.3."), (34, "Теорема 5.3.")]],
        10: [[(36, "Теорема 6.1.")]],
        11: [[(37, "Теорема 6.2.")]],
        12: [[(38, "Теорема 6.3"), (21, "Тригонометрические функции.")], [(38, "Теорема 6.3"), (21, "Тригонометрические функции."), (37, "Определение 6.1.")]],
    }
    questions, gold = [], []
    sections = re.findall(r"^## (\d+)\. ([^\n]+)\n(.*?)(?=^## |\Z)", markdown, flags=re.M | re.S)
    for number_text, title, body in sections:
        number = int(number_text)
        question = re.search(r"\*\*Вопрос\.\*\*\s*(.*?)(?=\n\s*-\s+\*\*[A-F]\.)", body, re.S).group(1).strip()
        options = [{"id": match.group(1), "text": match.group(2).strip()} for match in re.finditer(r"^\s*-\s+\*\*([A-F])\.\*\*\s*(.*?)(?=^\s*-\s+\*\*[A-F]\.\*\*|^\*\*Ответ:|\Z)", body, flags=re.M | re.S)]
        match = re.search(r"\*\*Ответ:\*\*\s*([^\n]+)\n(.*?)(?=\*\*Источник:)", body, re.S)
        abstain = "Отказ" in match.group(1)
        answer_ids = re.findall(r"\b[A-F]\b", match.group(1)) if not abstain else []
        category = re.search(r"\*\*Тип:\*\*\s*([^\.\n]+)", body).group(1).strip()
        identifier = f"q_{number:03d}"
        questions.append({"id": identifier, "question": question, "options": options})
        record = {"id": identifier, "category": CATEGORIES[category], "answer_ids": answer_ids, "abstain": abstain, "citation_sets": [[source(blocks, page, phrase) for page, phrase in entries] for entries in selectors.get(number, [])], "rationale": match.group(2).strip()}
        if abstain:
            record["missing_information"] = {13: "Значение постоянной функции", 14: "Направление обхода окружности", 15: "Сведения об аналитическом продолжении или особенностях функции"}[number]
        gold.append(record)
    if len(questions) != 15 or any(len(q["options"]) != 4 for q in questions):
        raise ValueError("Could not parse all 15 QA examples")
    return questions, gold


def own_dataset(blocks):
    specifications = [
        ("conditions", "Какие утверждения следуют из условий теорем о целых функциях?", ["Целая ограниченная функция постоянна.", "Голоморфная и ограниченная в единичном круге функция обязательно постоянна.", "Если целая f удовлетворяет |f(z)| ≤ M|z|² вне некоторого круга, то f — полином степени не выше 2.", "Любая целая ограниченная функция тождественно равна нулю."], ["A", "C"], [(37, "Следствие 6.1"), (37, "Теорема 6.2.")], "Теорема Лиувилля требует голоморфности во всей плоскости и не определяет значение константы. Теорема 6.2 с m=2 даёт степень не выше двух.", None),
        ("conditions", "f непрерывна в области D, которая не предполагается выпуклой. Какие дополнительные условия достаточны для голоморфности по теореме Морера?", ["Интеграл f по границе каждого треугольника, содержащегося вместе с замыканием в D, равен нулю.", "Интеграл f по одной окружности равен нулю.", "Интеграл f по границе одного треугольника равен нулю.", "Никаких: непрерывности уже достаточно."], ["A"], [(35, "Теорема 5.4")], "Теорема Морера требует нулевого интеграла по границе любого такого треугольника. Выпуклость всей области не требуется.", None),
        ("comparison", "f(z)=1/z в проколотом круге 0<|z|<2. Какие утверждения верны?", ["У f есть первообразная во всём проколотом круге.", "В достаточно малой окрестности каждой точки области первообразная существует.", "Интеграл по |z|=1 против часовой стрелки равен 2πi.", "Интеграл по любой замкнутой кривой равен нулю."], ["B", "C"], [(31, "Замечание 4.1."), (28, "= 2πi"), (26, "Теорема 4.1.")], "Локальная первообразная существует. Ненулевой интеграл по окружности исключает существование глобальной первообразной.", None),
        ("comparison", "f голоморфна в |z|<1. Сравните условия f(1/(n+2))=0 и f(n/(n+1))=0 для всех n≥1. Какие утверждения верны?", ["Первое условие влечёт f≡0.", "Второе условие само по себе позволяет применить теорему единственности с предельной точкой 1 внутри области.", "Нули ненулевой голоморфной функции не могут накапливаться внутри области.", "Для применения теоремы единственности достаточно бесконечности множества нулей без условий на предельную точку."], ["A", "C"], [(38, "Теорема 6.3")], "Первая последовательность стремится к 0 внутри круга. Вторая стремится к граничной точке 1, поэтому условие теоремы о внутренней предельной точке не выполнено.", None),
        ("calculation", "f голоморфна около 0 и f⁽³⁾(0)=24. Чему равен коэффициент c₃ при z³ в ряде Тейлора?", ["4", "8", "24", "12"], ["A"], [(36, "Теорема 6.1.")], "c₃=f⁽³⁾(0)/3!=24/6=4.", None),
        ("calculation", "Вычислите ∮ e^z/z⁴ dz по окружности |z|=1, проходимой один раз против часовой стрелки.", ["πi/3", "πi", "2πi", "0"], ["A"], [(20, "определяет"), (34, "Теорема 5.3.")], "По формуле Коши интеграл равен 2πi·(e^z)⁽³⁾(0)/3!=πi/3.", None),
        ("insufficient", "Известно, что f целая и |f(z)|≤5 во всей плоскости. Какое точное значение f(2) обязательно следует из этих данных? Если определить нельзя, верните отказ.", ["0", "1", "2", "5"], [], [], "Теорема Лиувилля даёт постоянство, но значение константы не задано: например, f≡0 и f≡1 удовлетворяют условиям.", "Значение константы или одно известное значение f"),
        ("insufficient", "f голоморфна в окрестности замкнутого единичного круга. Чему точно равен ∮ f(z)/z² dz по |z|=1 против часовой стрелки? Дополнительных значений f не дано; при недостаточности данных верните отказ.", ["0", "πi", "2πi", "4πi"], [], [], "Формула Коши даёт 2πi f′(0), но производная f′(0) неизвестна. Например, f≡0 и f(z)=z дают разные интегралы.", "Значение f′(0)"),
    ]
    questions, gold = [], []
    for number, (category, text, options, answers, selectors, rationale, missing) in enumerate(specifications, 1):
        identifier = f"own_{number:03d}"
        questions.append({"id": identifier, "question": text, "options": [{"id": letter, "text": option} for letter, option in zip("ABCD", options)]})
        record = {"id": identifier, "category": category, "answer_ids": answers, "abstain": missing is not None, "citation_sets": [[source(blocks, page, phrase) for page, phrase in selectors]] if selectors else [], "rationale": rationale}
        if missing:
            record["missing_information"] = missing
            record["supporting_blocks"] = [source(blocks, 37, "Следствие 6.1")] if number == 7 else [source(blocks, 34, "Теорема 5.3.")]
        gold.append(record)
    return questions, gold


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    data = destination / "homework_01_rag" / "data"
    data.mkdir(parents=True, exist_ok=True)
    pdf = args.pdf or data / "textbook.pdf"
    assignment = (ROOT / "homework_01_rag" / "materials" / "homework_01_rag.md").read_text(encoding="utf-8-sig")
    url = re.search(r"https://new\.mipt\.ru/[^)]+\.pdf", assignment).group(0)
    if not pdf.exists():
        urllib.request.urlretrieve(url, pdf)
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA256:
        raise ValueError("Textbook SHA256 does not match the pinned source")
    blocks = list(extract_corpus(pdf))
    write_jsonl(data / "corpus.jsonl", blocks)
    markdown = (ROOT / "homework_01_rag" / "materials" / "tfkp_15_qa.md").read_text(encoding="utf-8-sig")
    dev_questions, dev_gold = dev_dataset(markdown, blocks)
    own_questions, own_gold = own_dataset(blocks)
    for name, rows in [("dev_questions", dev_questions), ("dev_gold", dev_gold), ("own_questions", own_questions), ("own_gold", own_gold)]:
        write_jsonl(destination / f"{name}.jsonl", rows)
    manifest = {"source": url, "pdf_sha256": PDF_SHA256, "pdf_pages": 147, "blocks": len(blocks), "corpus_sha256": hashlib.sha256((data / "corpus.jsonl").read_bytes()).hexdigest(), "extractor": "PyMuPDF 1.26.7; font decoding and geometric fractions/overbars; no LLM"}
    (destination / "corpus_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"blocks": len(blocks), "dev_questions": len(dev_questions), "own_questions": len(own_questions)}))


if __name__ == "__main__":
    main()
