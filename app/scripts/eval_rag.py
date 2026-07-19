"""
Offline retrieval smoke test against golden_questions.jsonl.

Usage (from project root, with Qdrant populated and deps installed):
  python -m app.scripts.eval_rag

Exit code 1 if pass rate < --min-pass-rate (default 0.8).
Does not call Gemini — retrieval-only for stable CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.rag.retriever import RAGRetriever


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _load_golden(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _chunk_hits_keywords(chunk_text: str, keywords: list[str]) -> bool:
    low = chunk_text.lower()
    return any(k.lower() in low for k in keywords)


def run_eval(golden_path: Path, min_pass_rate: float) -> int:
    cases = _load_golden(golden_path)
    if not cases:
        print("No golden cases found.", file=sys.stderr)
        return 1

    retriever = RAGRetriever()
    passed = 0
    failed: list[str] = []

    for row in cases:
        qid = row.get("id", "?")
        query = row["query"]
        kws = row.get("must_contain_any") or []
        chunks = retriever.retrieve(query)
        texts = [c.text for c in chunks]
        ok = False
        if kws:
            ok = any(
                _chunk_hits_keywords(t, kws) for t in texts
            )
        else:
            ok = len(texts) > 0

        if ok:
            passed += 1
            print(f"  OK  [{qid}] {query[:60]}...")
        else:
            failed.append(qid)
            print(f"  FAIL [{qid}] {query[:60]}...")
            print(f"        keywords={kws!r} top_excerpt={texts[0][:120]!r}..." if texts else "        (no chunks)")

    rate = passed / len(cases)
    print()
    print(f"Result: {passed}/{len(cases)} passed ({rate:.0%}), threshold {min_pass_rate:.0%}")
    if rate < min_pass_rate:
        print(f"Failed IDs: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval against golden JSONL")
    parser.add_argument(
        "--golden",
        type=Path,
        default=_data_dir() / "golden_questions.jsonl",
        help="Path to golden_questions.jsonl",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.8,
        help="Minimum fraction of cases that must pass (default 0.8)",
    )
    args = parser.parse_args()
    if not args.golden.is_file():
        print(f"Golden file not found: {args.golden}", file=sys.stderr)
        sys.exit(1)
    sys.exit(run_eval(args.golden, args.min_pass_rate))


if __name__ == "__main__":
    main()
