"""Generate reproducible, uniquely solvable Sudoku regression fixtures.

Run from the repository root (after ``pip install -e .``)::

    python scripts/generate_puzzles.py
    python scripts/generate_puzzles.py --seed 20261029 --count-per-tier 36

The difficulty labels are operational classifications of THIS project's
verified logical-technique subsets, not standardized human difficulty ratings:

* easy: solvable using only naked/hidden singles;
* medium: not singles-only, but solvable using singles, locked candidates,
  and pairs/triples;
* hard: not basic, but solvable by adding selected fish/wing/link methods;
* expert: not solvable by the selected advanced subset (the full human solver
  may still solve it). It is NOT a proof that guessing is necessary.

This generator only accepts puzzles with exactly one solution according to
ReferenceSolver. All accepted solutions and metrics are independently checked.
No network, external puzzle datasets, or third-party Python packages needed.
Run scripts/rate_puzzles.py afterward to add full-solver rating metadata;
the generation and rating stages are intentionally separate.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from sudoku.core.board import SudokuBoard
from sudoku.solvers.constraint import ReferenceSolver
from sudoku.solvers.logical.solver import LogicalSolver
from sudoku.solvers.logical.singles import NakedSingle, HiddenSingle
from sudoku.solvers.logical.locked_candidates import Pointing, Claiming
from sudoku.solvers.logical.subsets import NakedPair, HiddenPair, NakedTriple, HiddenTriple
from sudoku.solvers.logical.fish import XWing
from sudoku.solvers.logical.strong_links import Skyscraper, TwoStringKite
from sudoku.solvers.logical.wings import XYWing
from sudoku.solvers.logical.coloring import SimpleColoring
from sudoku.solvers.logical.x_chains import XChain

# Avoid changing these without regenerating the dataset: tier definitions matter.
TIERS = ("easy", "medium", "hard", "expert")
TARGET_GIVENS = {
    "easy": (35, 43),
    "medium": (24, 32),
    "hard": (24, 30),
    "expert": (23, 29),
}
# Rotate the requested tier so the rarest category drives the attempt budget.
SINGLES = (NakedSingle, HiddenSingle)
BASIC = SINGLES + (Pointing, Claiming, NakedPair, HiddenPair, NakedTriple, HiddenTriple)
ADVANCED = BASIC + (XWing, Skyscraper, TwoStringKite, XYWing, SimpleColoring, XChain)

_ALL = (1 << 9) - 1
_BOX = tuple((i // 27) * 3 + (i % 9) // 3 for i in range(81))


def random_completed_grid(rng: random.Random) -> str:
    """Fill a randomized diagonal-box seed with randomized MRV backtracking.

    This constructs complete Sudoku grids, rather than merely renaming digits
    or exchanging rows of a fixed solved template.
    """
    cells = [0] * 81
    row_bits = [0] * 9
    col_bits = [0] * 9
    box_bits = [0] * 9

    def assign(i: int, digit: int) -> None:
        bit = 1 << (digit - 1)
        cells[i] = digit
        row_bits[i // 9] |= bit
        col_bits[i % 9] |= bit
        box_bits[_BOX[i]] |= bit

    def undo(i: int, digit: int) -> None:
        bit = 1 << (digit - 1)
        cells[i] = 0
        row_bits[i // 9] ^= bit
        col_bits[i % 9] ^= bit
        box_bits[_BOX[i]] ^= bit

    for box in (0, 4, 8):
        digits = list(range(1, 10))
        rng.shuffle(digits)
        start_row = (box // 3) * 3
        start_col = (box % 3) * 3
        for position, digit in enumerate(digits):
            i = 9 * (start_row + position // 3) + start_col + position % 3
            assign(i, digit)

    def fill() -> bool:
        smallest = 10
        tied: list[tuple[int, int]] = []
        for i, digit in enumerate(cells):
            if digit:
                continue
            mask = _ALL & ~(row_bits[i // 9] | col_bits[i % 9] | box_bits[_BOX[i]])
            count = mask.bit_count()
            if count == 0:
                return False
            if count < smallest:
                smallest = count
                tied = [(i, mask)]
            elif count == smallest:
                tied.append((i, mask))
        if not tied:
            return True
        i, mask = rng.choice(tied)
        digits = [d for d in range(1, 10) if mask & (1 << (d - 1))]
        rng.shuffle(digits)
        for digit in digits:
            assign(i, digit)
            if fill():
                return True
            undo(i, digit)
        return False

    if not fill():
        raise RuntimeError("Failed to construct a solved Sudoku grid")
    return "".join(map(str, cells))


def dig_unique_puzzle(solution: str, target: int, rng: random.Random,
                      oracle: ReferenceSolver) -> str:
    """Randomly remove clues; keep removal iff exactly one completion remains.

    A single randomized deletion pass need not hit the target number of clues;
    such puzzles can still be accepted into their measured difficulty tier.
    """
    cells = list(solution)
    positions = list(range(81))
    rng.shuffle(positions)
    givens = 81
    for i in positions:
        if givens <= target:
            break
        digit = cells[i]
        cells[i] = "0"
        if oracle.count_solutions("".join(cells), limit=2) == 1:
            givens -= 1
        else:
            cells[i] = digit
    return "".join(cells)


def difficulty_evaluators() -> dict[str, LogicalSolver]:
    return {
        "singles": LogicalSolver(techniques=[cls() for cls in SINGLES]),
        "basic": LogicalSolver(techniques=[cls() for cls in BASIC]),
        "advanced": LogicalSolver(techniques=[cls() for cls in ADVANCED]),
    }


def classify(puzzle: str, solvers: dict[str, LogicalSolver]) -> tuple[str, dict]:
    """Return the lowest solving technique tier, plus its reproducible profile."""
    board = SudokuBoard.from_string(puzzle)
    profile: dict[str, dict] = {}
    for name, tier in (("singles", "easy"), ("basic", "medium"), ("advanced", "hard")):
        result = solvers[name].solve(board)
        profile[name] = {"status": result.status.value, "steps": len(result.steps)}
        if result.solved:
            return tier, profile
    return "expert", profile


def generate(count_per_tier: int, seed: int, max_attempts: int) -> tuple[list[dict], int]:
    rng = random.Random(seed)
    oracle = ReferenceSolver()
    solvers = difficulty_evaluators()
    found: dict[str, list[dict]] = {tier: [] for tier in TIERS}
    seen: set[str] = set()

    attempts_used = 0
    for attempt in range(1, max_attempts + 1):
        if all(len(records) >= count_per_tier for records in found.values()):
            break
        attempts_used = attempt
        # Prefer the rarest unsatisfied class, but vary all target clue counts.
        missing = [tier for tier in TIERS if len(found[tier]) < count_per_tier]
        requested = rng.choice(missing)
        low, high = TARGET_GIVENS[requested]
        target = rng.randint(low, high)
        solution = random_completed_grid(rng)
        puzzle = dig_unique_puzzle(solution, target, rng, oracle)
        if puzzle in seen:
            continue
        seen.add(puzzle)
        tier, profile = classify(puzzle, solvers)
        if len(found[tier]) >= count_per_tier:
            continue
        result = oracle.analyze(puzzle, limit=2)
        if not result.is_unique or result.solutions != (solution,):
            raise AssertionError("Generator produced an inconsistent or non-unique puzzle")
        # The dataset is reproducible from the seed and generation settings.
        found[tier].append({
            "id": f"{tier.upper()}-{len(found[tier]) + 1:03d}",
            "difficulty": tier,
            "puzzle": puzzle,
            "solution": solution,
            "givens": 81 - puzzle.count("0"),
            "logical_profile": profile,
            "reference_nodes": result.statistics.nodes,
            "reference_branches": result.statistics.branches,
        })

    short = {tier: len(found[tier]) for tier in TIERS if len(found[tier]) < count_per_tier}
    if short:
        raise RuntimeError(f"Exhausted {max_attempts} generation attempts; incomplete tiers: {short}")
    return [record for tier in TIERS for record in found[tier]], attempts_used


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--count-per-tier", type=int, default=36)
    parser.add_argument("--max-attempts", type=int, default=10000)
    parser.add_argument("--output", type=Path, default=Path("data/puzzles.jsonl"))
    args = parser.parse_args()
    if args.count_per_tier < 1 or args.max_attempts < 1:
        parser.error("--count-per-tier and --max-attempts must be positive")
    records, attempts = generate(args.count_per_tier, args.seed, args.max_attempts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"Saved {len(records)} unique-solution puzzles to {args.output} "
          f"after {attempts} attempts. Tier counts: {dict(Counter(r['difficulty'] for r in records))}")


if __name__ == "__main__":
    main()
