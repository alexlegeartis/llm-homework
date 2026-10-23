import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from .common import read_jsonl
from .predict import validate_answer


CATEGORIES = ["conditions", "comparison", "calculation", "insufficient"]


def f1(predicted, expected):
    predicted, expected = set(predicted), set(expected)
    return 2 * len(predicted & expected) / (len(predicted) + len(expected)) if predicted or expected else 1.0


def evaluate(questions, gold, answers, traces, block_ids, no_context=False, reference_cost=None):
    expected_ids = [q["id"] for q in questions]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Duplicate question ID")
    gold_by_id = {row["id"]: row for row in gold}
    if set(gold_by_id) != set(expected_ids) or len(gold_by_id) != len(gold):
        raise ValueError("Gold IDs do not match question IDs")
    counts = Counter(row.get("id") for row in answers)
    trace_counts = Counter(row.get("id") for row in traces)
    by_id = {row.get("id"): row for row in answers}
    trace_by_id = {row.get("id"): row for row in traces}
    efficiency_valid = not (set(counts) - set(expected_ids) or set(trace_counts) - set(expected_ids))
    details = []
    costs, input_tokens, output_tokens, calls, latency = [], [], [], [], []
    category_scores = defaultdict(list)
    for question in questions:
        identifier = question["id"]
        target = gold_by_id[identifier]
        answer = by_id.get(identifier)
        trace = trace_by_id.get(identifier)
        errors = []
        if counts[identifier] != 1:
            errors.append("Missing or duplicate answer")
        if answer:
            errors += validate_answer(answer, question, block_ids, no_context)
        if trace_counts[identifier] != 1 or trace is None:
            errors.append("Missing or duplicate trace")
            efficiency_valid = False
        trace = trace or {}
        for key in ["llm_calls", "input_tokens", "output_tokens"]:
            if type(trace.get(key)) is not int or trace[key] < 0:
                errors.append(f"Invalid trace counter: {key}")
                efficiency_valid = False
        spent_in = trace.get("input_tokens", 0)
        spent_out = trace.get("output_tokens", 0)
        spent_calls = trace.get("llm_calls", 0)
        if not trace.get("usage_verified"):
            errors.append("Unverified usage")
            efficiency_valid = False
        if trace.get("error"):
            errors.append("Processing error")
        if any(not isinstance(value, (int, float)) for value in [spent_in, spent_out, spent_calls]):
            spent_in = spent_out = spent_calls = 0
        over_limit = spent_calls > 4 or spent_in > 16384 or spent_out > 4096
        request_usage = trace.get("calls", [])
        if len(request_usage) != spent_calls:
            errors.append("Incomplete per-call accounting")
            efficiency_valid = False
        elif sum(call.get("input_tokens", 0) for call in request_usage) != spent_in or sum(call.get("output_tokens", 0) for call in request_usage) != spent_out:
            errors.append("Per-call usage does not match totals")
            efficiency_valid = False
        for call in request_usage:
            if call.get("input_tokens", 0) + call.get("max_tokens", 0) > 8192:
                over_limit = True
        if over_limit:
            errors.append("Computational limit exceeded")
            efficiency_valid = False
        accuracy = int(not errors and answer is not None and answer["abstain"] == target["abstain"] and set(answer["answer_ids"]) == set(target["answer_ids"]))
        citation_f1 = 0.0
        if accuracy and not target["abstain"] and not no_context:
            citation_f1 = max((f1(answer["citations"], acceptable) for acceptable in target["citation_sets"]), default=0.0)
        score = float(accuracy) if target["abstain"] or no_context else accuracy * (0.8 + 0.2 * citation_f1)
        category_scores[target["category"]].append(score)
        cost = spent_in + 4 * spent_out + 256 * spent_calls
        costs.append(cost)
        input_tokens.append(spent_in)
        output_tokens.append(spent_out)
        calls.append(spent_calls)
        latency.append(trace.get("elapsed_ms", 0))
        details.append({"id": identifier, "category": target["category"], "answer_accuracy": accuracy, "citation_f1": citation_f1, "score": score, "errors": errors})
    quality = None if no_context else statistics.mean(statistics.mean(category_scores[category]) if category_scores.get(category) else 0 for category in CATEGORIES)
    mean_cost = statistics.mean(costs)
    efficiency = None if reference_cost is None else min(1, reference_cost / max(mean_cost, 1)) if efficiency_valid else 0.0
    return {"answer_accuracy": statistics.mean(row["answer_accuracy"] for row in details), "Q": quality, "mean_input_tokens": statistics.mean(input_tokens), "mean_output_tokens": statistics.mean(output_tokens), "mean_llm_calls": statistics.mean(calls), "mean_cost": mean_cost, "median_latency_ms": statistics.median(latency), "efficiency_valid": efficiency_valid, "E": efficiency, "score": None if quality is None or efficiency is None else 75 * quality + 25 * quality * efficiency, "category_scores": {category: statistics.mean(values) for category, values in category_scores.items()}, "questions": details}


def main():
    parser = argparse.ArgumentParser()
    for name in ["questions", "gold", "answers", "trace", "corpus"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output")
    parser.add_argument("--reference-cost", type=float)
    parser.add_argument("--no-context", action="store_true")
    args = parser.parse_args()
    metrics = evaluate(read_jsonl(args.questions), read_jsonl(args.gold), read_jsonl(args.answers), read_jsonl(args.trace), [b["block_id"] for b in read_jsonl(args.corpus)], args.no_context, args.reference_cost)
    content = json.dumps(metrics, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(content + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in metrics.items() if key not in {"questions", "category_scores"}}))


if __name__ == "__main__":
    main()
