"""Reproducible small-scale comparisons of exact Sudoku solvers.

From the project root:
    PYTHONPATH=src python scripts/benchmark_constraint.py --repeats 5

Times measure each backend's analyze() search-timing window (domain setup is
excluded by the propagation backend).
They are not reliable across machines. Node and failure counts use different
conventions in each solver; compare them only within the same implementation.
"""

from __future__ import annotations

import argparse
from statistics import median
from sudoku.solvers.constraint import PropagationSolver, ReferenceSolver

PUZZLES = {
    "classic": "530070000600195000098000060800060003400803001700020006060000280000419005000080079",
    "medium": "200080300060070084030500209000105408000000000402706000301007040720040060004010003",
    "sparse": "000000010400000000020000000000050407008000300001090000300400200050100000000806000",
    "hard_a": "005000987040050001007000000200048000090100000600200000300600200000009070000000500",
    "hard_b": "023700006800060590900000700000040970307096002000000000500470000000002000080000000",
}


def run(repeats: int = 3) -> None:
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be positive")
    solvers = {
        "reference": ReferenceSolver(),
        "propagation_mrv": PropagationSolver(),
        "propagation_mrv_degree": PropagationSolver(variable_heuristic="mrv_degree"),
        "propagation_mrv_degree_lcv": PropagationSolver(variable_heuristic="mrv_degree", value_heuristic="lcv"),
    }
    print("puzzle,algorithm,median_seconds,median_nodes,median_branches,median_failed_branches,solutions,exhaustive")
    for puzzle_name, puzzle in PUZZLES.items():
        oracle = ReferenceSolver().analyze(puzzle)
        for algorithm, solver in solvers.items():
            observations = [solver.analyze(puzzle) for _ in range(repeats)]
            for result in observations:
                if (result.solution_count != oracle.solution_count
                        or result.is_unique != oracle.is_unique
                        or result.is_unsatisfiable != oracle.is_unsatisfiable
                        or result.has_multiple_solutions != oracle.has_multiple_solutions):
                    raise AssertionError(f"{algorithm} disagrees with reference on {puzzle_name}")
                # When the answer is unique, the exact completed grid must match.
                if oracle.is_unique and result.solutions != oracle.solutions:
                    raise AssertionError(f"{algorithm} produced an unexpected solution")
            sample = observations[0]
            stats = [r.statistics for r in observations]
            branches = [getattr(s, "decisions", getattr(s, "branches", 0)) for s in stats]
            failed = [getattr(s, "backtracks", getattr(s, "dead_ends", 0)) for s in stats]
            print(
                f"{puzzle_name},{algorithm},{median(s.elapsed_seconds for s in stats):.6f},"
                f"{median(s.nodes for s in stats):g},{median(branches):g},{median(failed):g},"
                f"{sample.solution_count},{str(sample.exhaustive).lower()}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    run(parser.parse_args().repeats)
