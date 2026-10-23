from dataclasses import dataclass, replace
import re

import pymupdf


@dataclass
class Glyph:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    size: float
    math: bool
    order: int
    block: int
    line: int


EXTENSION = {
    "P": "Σ", "X": "Σ", "Q": "Π", "Y": "Π", "R": "∫", "Z": "∫",
    "H": "∮", "I": "∮", "S": "∪", "[": "∪", "T": "∩", "\\": "∩",
    "\x12": "(", "\x13": ")", "\x00": "(", "\x01": ")",
    "\x02": "[", "\x03": "]", "\x08": "{", "\x09": "}",
    "\x0c": "|", "\x0d": "|", "\x0e": "/", "\x0f": "\\",
    "\x10": "(", "\x11": ")", "\x14": "[", "\x15": "]",
    "\x16": "{", "\x17": "}", "\x1a": "{", "\x1b": "}",
    "\uf8eb": "(", "\uf8ec": "", "\uf8ed": "", "\uf8f6": ")",
    "\uf8f7": "", "\uf8f8": "", "\uf8ee": "[", "\uf8ef": "",
    "\uf8f0": "", "\uf8f9": "]", "\uf8fa": "", "\uf8fb": "",
}


def decode(text, font):
    if re.fullmatch(r"F\d+", font):
        replacements = {"\x02": "", "\x15": "–", "\x16": "—", "\x9f": "§"}
        return "".join(replacements.get(c, bytes([ord(c)]).decode("cp1251", errors="replace") if 128 <= ord(c) <= 255 else c) for c in text)
    if font.startswith("CMEX"):
        return "".join(EXTENSION.get(c, c if ord(c) >= 32 else "") for c in text)
    if font.startswith("MSBM"):
        return text.translate(str.maketrans({"C": "ℂ", "R": "ℝ", "N": "ℕ", "Z": "ℤ"}))
    return text.replace("\x00", "").replace("\x01", "").replace("̸=", "≠")


def render(glyphs):
    result = []
    previous = None
    script = None
    for glyph in sorted(glyphs, key=lambda g: g.order):
        text = glyph.text
        if not text or (glyph.math and glyph.size < 8.5 and not text.strip()):
            continue
        mode = None
        if glyph.math and glyph.size < 8.5 and previous and previous.math:
            if glyph.baseline < previous.baseline - 1.1:
                mode = "^"
            elif glyph.baseline > previous.baseline + 1.1:
                mode = "_"
        if mode != script:
            if script:
                result.append("}")
            if mode:
                result.append(mode + "{")
            script = mode
        if not mode and previous and glyph.line != previous.line:
            result.append("\n")
        result.append(text)
        if not mode and text.strip():
            previous = glyph
    if script:
        result.append("}")
    value = "".join(result)
    value = re.sub(r"([а-яё])-\s*\n\s*([а-яё])", r"\1\2", value)
    return re.sub(r"\s+", " ", value).strip()


def page_paragraphs(page):
    glyphs = []
    order = 0
    for block_id, block in enumerate(page.get_text("rawdict")["blocks"]):
        for line_id, line in enumerate(block.get("lines", [])):
            for span in line["spans"]:
                for char in span["chars"]:
                    text = decode(char["c"], span["font"])
                    x0, y0, x1, y1 = char["bbox"]
                    if char["origin"][1] < 35 or char["origin"][1] > page.rect.height - 18:
                        continue
                    glyphs.append(Glyph(text, x0, y0, x1, y1, char["origin"][1], span["size"], not span["font"].startswith("F"), order, block_id, line_id))
                    order += 1
    rules = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l" and abs(item[1].y - item[2].y) < 0.2:
                x0, x1 = sorted([item[1].x, item[2].x])
                if 2 < x1 - x0 < 220:
                    rules.append((x0, x1, item[1].y))
    fraction_rules = []
    for x0, x1, y in rules:
        targets = [g for g in glyphs if g.math and g.size > 8.5 and re.fullmatch(r"[a-zα-ω]", g.text) and x0 - 0.5 <= g.x0 <= g.x1 <= x1 + 0.5 and 4.4 < g.baseline - y < 7.5]
        if targets and x1 - x0 < 55:
            first = min(targets, key=lambda g: g.order)
            last = max(targets, key=lambda g: g.order)
            first.text = "bar(" + first.text
            last.text += ")"
        else:
            fraction_rules.append((x0, x1, y))
    for x0, x1, y in sorted(fraction_rules, key=lambda r: r[1] - r[0]):
        candidates = [g for g in glyphs if g.math and g.text.strip() and x0 - 0.8 <= (g.x0 + g.x1) / 2 <= x1 + 0.8]
        above = [g for g in candidates if 0.8 < y - g.baseline < 20]
        below = [g for g in candidates if 3 < g.baseline - y < 20]
        if not above or not below:
            continue
        def row(items, upper):
            largest = max(g.size for g in items)
            baselines = [g.baseline for g in items if g.size >= largest - 0.1]
            baseline = max(baselines) if upper else min(baselines)
            return [g for g in items if baseline - 7 < g.baseline < baseline + 4]
        numerator, denominator = row(above, True), row(below, False)
        selected = {g.order for g in numerator + denominator}
        first = min(numerator + denominator, key=lambda g: g.order)
        fraction = replace(first, text=f"({render(numerator)})/({render(denominator)})", x0=x0, x1=x1, baseline=y + 2.49, size=9.96)
        glyphs = [g for g in glyphs if g.order not in selected] + [fraction]
    paragraphs = []
    for block_id in sorted({g.block for g in glyphs}):
        text = render([g for g in glyphs if g.block == block_id])
        if text and not re.fullmatch(r"\d+", text):
            paragraphs.append(text)
    return paragraphs


HEADINGS = re.compile(r"^(?:(?:Теорема|Следствие|Лемма|Определение|Замечание|Пример|Доказательство)\b|§)")


def extract_corpus(pdf):
    document = pymupdf.open(pdf)
    section = "Содержание"
    for page_number, page in enumerate(document, 1):
        paragraphs = page_paragraphs(page)
        buffer = []
        groups = []
        for paragraph in paragraphs:
            if HEADINGS.match(paragraph) and buffer:
                groups.append((section, " ".join(buffer)))
                buffer = []
            if re.match(r"§\s*\d+\.", paragraph):
                section = paragraph[:100]
            buffer.append(paragraph)
            if sum(map(len, buffer)) >= 850:
                groups.append((section, " ".join(buffer)))
                buffer = []
        if buffer:
            groups.append((section, " ".join(buffer)))
        pieces = []
        for group_section, text in groups:
            while len(text) > 1500:
                split = max(text.rfind(". ", 650, 1400), text.rfind("; ", 650, 1400))
                split = split + 1 if split >= 0 else text.rfind(" ", 0, 1300)
                pieces.append((group_section, text[:split].strip()))
                text = text[split:].strip()
            if text:
                pieces.append((group_section, text))
        for i, (group_section, text) in enumerate(pieces, 1):
            yield {"block_id": f"p{page_number:04d}_b{i:03d}", "page": page_number, "section": group_section, "text": text}
