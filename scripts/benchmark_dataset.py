"""Benchmark the generated Sudoku dataset against independent backends.

From project root (after ``pip install -e .``)::

    python scripts/benchmark_dataset.py --per-tier 5 --repeats 3
    python scripts/benchmark_dataset.py --per-tier 0 --algorithms reference propagation exact_cover
    python scripts/benchmark_dataset.py --algorithms integer_programming --per-tier 5
    python scripts/benchmark_dataset.py --algorithms hybrid --hybrid-backend exact_cover

CSV rows are emitted to stdout; all solutions are checked against the saved
unique completion. Times are wall-clock process measurements and should be
compared on one machine with consistent settings, never across hardware.
Cross-algorithm node counts use different definitions and are NOT comparable.
The hybrid mode runs the full verified human-logic engine; it can be much
slower than mathematical-only solving on expert-classified puzzles.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import median
from time import perf_counter

from sudoku.solvers.constraint import ConstraintSolver
from sudoku.solvers.hybrid import HybridSolver

TIERS = ("easy", "medium", "hard", "expert")
ALGORITHMS = ("reference", "propagation", "exact_cover", "integer_programming", "hybrid")


def load_puzzles(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("Dataset is empty")
    return records


def benchmark(path: Path, *, per_tier: int, repeats: int, algorithms: list[str],
              hybrid_backend: str) -> None:
    if per_tier < 0 or repeats < 1:
        raise ValueError("per-tier must be nonnegative and repeats must be positive")
    records = load_puzzles(path)
    selected = [r for tier in TIERS for r in [x for x in records if x["difficulty"] == tier][:per_tier or None]]
    solvers = {
        name: (HybridSolver(mode="hybrid", constraint_algorithm=hybrid_backend)
               if name == "hybrid" else ConstraintSolver(algorithm=name))
        for name in algorithms
    }

    writer = csv.DictWriter(sys.stdout, fieldnames=(
        "id", "difficulty", "givens", "algorithm", "median_seconds", "median_search_nodes",
        "status", "used_fallback", "logical_steps",
    ))
    writer.writeheader()
    for record in selected:
        for name, solver in solvers.items():
            elapsed: list[float] = []
            nodes: list[int] = []
            for _ in range(repeats):
                start = perf_counter()
                if name == "hybrid":
                    result = solver.solve(record["puzzle"], solution_limit=2)
                    solution = result.first_solution
                    stats = result.constraint_result.statistics if result.constraint_result is not None else None
                else:
                    result = solver.analyze(record["puzzle"], limit=2)
                    solution = result.first_solution
                    stats = result.statistics
                    if not result.is_unique:
                        raise AssertionError(f"{name} did not certify uniqueness for {record['id']}")
                elapsed.append(perf_counter() - start)
                if solution is None or solution.to_string() != record["solution"]:
                    raise AssertionError(f"{name} disagrees with stored solution for {record['id']}")
                if stats is not None:
                    count = getattr(stats, "nodes", getattr(stats, "mip_nodes", None))
                    if count is not None:
                        nodes.append(count)
            writer.writerow({
                "id": record["id"], "difficulty": record["difficulty"], "givens": record["givens"],
                "algorithm": name, "median_seconds": f"{median(elapsed):.6f}",
                "median_search_nodes": f"{median(nodes):g}" if nodes else "NA",
                "status": "solved", "used_fallback": str(result.used_fallback).lower() if name == "hybrid" else "NA",
                "logical_steps": len(result.steps) if name == "hybrid" else "NA",
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/puzzles.jsonl"))
    parser.add_argument("--per-tier", type=int, default=5, help="Puzzles per tier; 0 means all")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--algorithms", nargs="+", choices=ALGORITHMS,
                        default=["reference", "propagation", "exact_cover"])
    parser.add_argument("--hybrid-backend", choices=ALGORITHMS[:-1], default="propagation")
    args = parser.parse_args()
    benchmark(args.data, per_tier=args.per_tier, repeats=args.repeats,
              algorithms=list(dict.fromkeys(args.algorithms)), hybrid_backend=args.hybrid_backend)


if __name__ == "__main__":
    main()
