# Independent reference solver

The module `sudoku.solvers.constraint.reference` provides a standalone exact
Sudoku solver based on recursive backtracking, Minimum Remaining Values (MRV),
and row/column/box bitmasks. It deliberately does **not** import the logical
techniques, `CandidateState`, or `DeductionVerifier`.

## API

```python
from sudoku.core.board import SudokuBoard
from sudoku.solvers.constraint import ReferenceSolver

puzzle = SudokuBoard.from_string(
    "530070000600195000098000060800060003400803001"
    "700020006060000280000419005000080079"
)

oracle = ReferenceSolver()
answer = oracle.solve(puzzle)           # SudokuBoard or None
analysis = oracle.analyze(puzzle)        # default limit=2
print(analysis.solutions)
print(analysis.is_unique)               # True only when established
print(analysis.has_multiple_solutions)  # True when >=2 solutions found
print(analysis.statistics)

# Truth checks for future verifier auditing (zero-based coordinates):
print(oracle.allows_candidate(puzzle, 0, 2, 4))
print(oracle.forces_placement(puzzle, 0, 2, 4))
print(oracle.proves_elimination(puzzle, 0, 2, 1))
```

`analyze(limit=2)` can establish exactly three useful outcomes:

- **Unsolvable**: the search finishes and finds no solution.
- **Unique**: the search finishes with exactly one solution.
- **Multiple**: at least two solutions are found (search may stop early).

A truncated search with one solution does not prove uniqueness. In particular,
`limit=1` deliberately returns `is_unique=False` even for a unique puzzle.

`count_solutions()` reports a count **up to a cap**, not an unrestricted count.

## Testing a deduction as a theorem

Suppose the original clues form a constraint set `P`, and a logical technique
claims that candidate `d` can be removed from cell `(r,c)`.
The independent correctness test is

```
P AND (cell[r,c] = d)  is UNSAT
```

For a claimed placement, verify

```
P AND (cell[r,c] != d) is UNSAT
```

Both entailment methods also check that `P` has **at least one solution**,
so no contradictory puzzle is treated as vacuously proving every move.

Use the **original puzzle**, not a board containing unverified placements:

```python
from sudoku.solvers.logical.solver import LogicalSolver

original = puzzle.to_string()
trace = LogicalSolver().solve(puzzle)
for step in trace.steps:
    for move in step.deduction.placements:
        assert oracle.forces_placement(original, *move.cell, move.digit)
    for move in step.deduction.eliminations:
        assert oracle.proves_elimination(original, *move.cell, move.digit)
```

See `tests/solvers/constraint/test_reference_oracle.py` for integration tests
using three of the bundled UI example puzzles.

## Performance and safety

- The implementation is deterministic and uses pure Python with no runtime
  dependencies.
- Counting **up to two solutions** is usually inexpensive, but some difficult
  unsatisfiable puzzles may take longer because the search is exhaustive.
- Do not run expensive solution-counting calls synchronously in the local UI
  server's globally locked request handler. Use offline tests or a separately
  bounded asynchronous workflow if an interactive oracle is added later.
- This oracle validates the *truth* of a deduction, but does not yet check
  whether the named human technique or its premise explanation is accurate.
- The reference solver is not wired into production `DeductionVerifier` yet.
  Keeping it independent makes it suitable for catching shared logic errors.

## Next verifier-refactor stage

1. Introduce machine-checkable **proof witnesses** for each technique family.
2. Audit each proposed effect against the reference solver in regression tests.
3. Refactor fish, wing, rectangle, and locked-candidate verification to check
   witnesses **without calling the detection algorithm again**.
4. Keep the oracle as a testing/audit facility rather than making an
   exponential global search mandatory for every interactive hint.
