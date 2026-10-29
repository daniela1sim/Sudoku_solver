"""Enrich an existing Sudoku JSONL corpus with *local* human-logic ratings.

This reuses sudoku.solvers.logical.rating.estimate_rating; it does NOT
reimplement technique weights or assign arbitrary scores to stuck puzzles.
Original puzzle records, solutions, tiers, and IDs are left untouched.

From the project root (Python 3.10+, with PYTHONPATH=src or installed package)::

    python scripts/rate_puzzles.py
    python scripts/rate_puzzles.py --input data/puzzles.jsonl --output data/rated.jsonl
    python scripts/rate_puzzles.py --timeout-seconds 15 --force

The default input and output are both data/puzzles.jsonl. Each result is saved
atomically as soon as its puzzle finishes, so the command can be interrupted
and resumed without losing completed work. A process per puzzle ensures that
advanced-technique searches can be terminated on timeout on Windows and Linux.
Timeout is a computational safety bound, NOT a Sudoku difficulty assessment.

Ratings are local, solve-path dependent and not official Sudoku Explainer scores.
A final score is only present when the full logical solver completed the grid.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
from typing import Any

from sudoku.core.board import SudokuBoard
from sudoku.solvers.logical.rating import estimate_rating
from sudoku.solvers.logical.solver import LogicalSolver

RATING_METHOD = "local-technique-v1"
DEFAULT_TIMEOUT_SECONDS = 10.0


def rating_config(*, max_steps: int | None = None) -> dict[str, Any]:
    """Pin the logical engine settings that materially influence the rating."""
    return {
        "techniques": "default",  # LogicalSolver() with its entire default registry
        "allow_uniqueness": False,
        "max_steps": max_steps,
    }


def rate_puzzle(puzzle: str, *, max_steps: int | None = None) -> dict[str, Any]:
    """Run the full default logical solver and report a reproducible local rating.

    This function itself has no wall-clock bound. The CLI uses a separate
    worker process for each puzzle to enforce a timeout.
    """
    if max_steps is not None and (type(max_steps) is not int or max_steps < 0):
        raise ValueError("max_steps must be a nonnegative integer or None")
    board = SudokuBoard.from_string(puzzle)
    result = LogicalSolver(allow_uniqueness=False).solve(board, max_steps=max_steps)
    rating = estimate_rating(result.steps, complete=result.solved)
    # A full score is warranted only by a successful, complete human solve.
    if result.status.value == "step_limit":
        rating["status"] = "step_limit"
        rating["score"] = None
    rating["config"] = rating_config(max_steps=max_steps)
    rating["logical_status"] = result.status.value
    rating["steps"] = len(result.steps)
    rating["placements"] = sum(len(step.deduction.placements) for step in result.steps)
    rating["eliminations"] = sum(len(step.deduction.eliminations) for step in result.steps)
    rating["technique_counts"] = dict(sorted(Counter(step.deduction.technique for step in result.steps).items()))
    return rating


def _worker(puzzle: str, max_steps: int | None, send) -> None:
    """Child process target: communicate only JSON-friendly values."""
    try:
        send.send(("ok", rate_puzzle(puzzle, max_steps=max_steps)))
    except Exception as exc:
        send.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        send.close()


def rate_with_timeout(puzzle: str, *, timeout_seconds: float,
                      max_steps: int | None = None) -> dict[str, Any]:
    """Enforce a per-puzzle timeout without leaving a runaway technique search.

    Timed-out/error runs cannot support an observed peak, so both scores are
    null. Other puzzle records continue to be processed.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    ctx = mp.get_context("spawn")
    recv, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_worker, args=(puzzle, max_steps, send))
    try:
        proc.start()
    except BaseException:
        recv.close()
        send.close()
        raise
    send.close()
    try:
        if recv.poll(timeout_seconds):
            try:
                state, result = recv.recv()
            except EOFError:
                state, result = "error", "Worker terminated before returning a rating"
            proc.join(timeout=0.5)
            if state == "ok":
                return result
            failure_status = "error"
            failure_message = result
        else:
            failure_status = "timeout"
            failure_message = None
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1)
            if proc.is_alive():
                proc.kill()
                proc.join()
        from sudoku.solvers.logical.rating import SCALE_MAX
        output = {
            "method": RATING_METHOD, "scale_max": SCALE_MAX,
            "status": failure_status, "score": None,
            "observed_peak": None, "hardest_technique": None,
            "config": rating_config(max_steps=max_steps),
            "logical_status": None, "steps": None, "placements": None,
            "eliminations": None, "technique_counts": None,
        }
        if failure_message is not None:
            output["error"] = failure_message
        return output
    finally:
        recv.close()
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1)


def read_records(path: Path) -> list[dict]:
    """Load existing JSONL, preserving record order and all unrelated keys."""
    with path.open("r", encoding="utf-8") as source:
        records = [json.loads(line) for line in source if line.strip()]
    if not records:
        raise ValueError(f"No puzzle records in {path}")
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Puzzle IDs must be unique")
    for record in records:
        SudokuBoard.from_string(record["puzzle"])
    return records


def write_records_atomic(path: Path, records: list[dict]) -> None:
    """Never expose a partially written JSONL file to other consumers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as output:
            temp_path = Path(output.name)
            for record in records:
                output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def is_current(rating: Any, *, max_steps: int | None) -> bool:
    return (isinstance(rating, dict)
            and rating.get("method") == RATING_METHOD
            and rating.get("config") == rating_config(max_steps=max_steps))


def enrich_records(records: list[dict], *, timeout_seconds: float,
                   max_steps: int | None = None, force: bool = False,
                   save_to: Path | None = None,
                   ids: frozenset[str] | None = None) -> Counter:
    """Add rating metadata; support resumable/partial dataset updates."""
    counts: Counter = Counter()
    for number, record in enumerate(records, start=1):
        if ids is not None and record["id"] not in ids:
            continue
        if not force and is_current(record.get("rating"), max_steps=max_steps):
            counts["skipped"] += 1
            continue
        rating = rate_with_timeout(record["puzzle"], timeout_seconds=timeout_seconds,
                                   max_steps=max_steps)
        record["rating"] = rating
        counts[rating["status"]] += 1
        print(f"[{number}/{len(records)}] {record['id']}: {rating['status']} "
              f"({rating['score'] if rating['score'] is not None else 'unrated'})", flush=True)
        if save_to is not None:
            write_records_atomic(save_to, records)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/puzzles.jsonl"))
    parser.add_argument("--output", type=Path, default=None,
                        help="Default: update --input atomically in place")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-steps", type=int, default=None,
                        help="Optional logical deduction limit; a limit produces no final rating")
    parser.add_argument("--force", action="store_true", help="Recalculate existing ratings")
    parser.add_argument("--ids", nargs="+", default=None, help="Only rate specified puzzle IDs")
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.max_steps is not None and args.max_steps < 0:
        parser.error("--timeout-seconds must be positive and --max-steps nonnegative")
    destination = args.output if args.output is not None else args.input
    records = read_records(args.input)
    if destination != args.input:
        # Save the complete input immediately, even if every record is skipped.
        write_records_atomic(destination, records)
    counts = enrich_records(records, timeout_seconds=args.timeout_seconds,
                            max_steps=args.max_steps, force=args.force,
                            save_to=destination,
                            ids=frozenset(args.ids) if args.ids is not None else None)
    print(f"Rated dataset: {dict(counts)}. Output: {destination}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
