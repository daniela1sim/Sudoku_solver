# Constraint solvers: propagation and Algorithm X (backend only)

The project now has three independent *algorithms* that solve ordinary Sudoku puzzles:

- `ReferenceSolver`: the original, isolated MRV/bitmask backtracker. **Keep this untouched as a correctness oracle** for verifying deductions made by the logical solver. It accepts a clue-based `SudokuBoard` or string and optional explicit forced/forbidden assumptions.
- `PropagationSolver`: an incremental domain-filtering solver with naked-single and hidden-single propagation followed by deterministic depth-first search. It accepts a string, `SudokuBoard`, **or `CandidateState`**. It assumes candidate eliminations already represented by the state are correct; it does not verify human deductions.
- `ExactCoverSolver`: a sparse Algorithm X implementation with reversible cover/uncover operations and deterministic minimum-column selection. It also accepts strings, `SudokuBoard` and `CandidateState` without mutating the inputs. It does not import or invoke the other algorithms or the deduction verifier.

The `ConstraintSolver` facade selects a mathematical backend. These additions do **not** change the web UI, app services, or the logical solver.

## Usage

```python
from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.solvers.constraint import ConstraintSolver, PropagationSolver, ExactCoverSolver

puzzle = SudokuBoard.from_string(
    "530070000600195000098000060800060003400803001"
    "700020006060000280000419005000080079"
)

solver = ConstraintSolver(
    algorithm="propagation",
    variable_heuristic="mrv_degree",
    value_heuristic="lcv",
)
analysis = solver.analyze(puzzle, limit=2)
print(analysis.is_unique, analysis.first_solution, analysis.statistics)

# For future logical-first fallback: preserve both placed values AND eliminations.
state = CandidateState(puzzle)
# ... apply only verified deductions to state ...
answer = PropagationSolver().solve(state)

# Independent oracle for clue-based validation (no candidate-state coupling).
reference = ConstraintSolver(algorithm="reference")
assert reference.solve(puzzle).to_string() == answer.to_string()

# Algorithm X: same public facade; it preserves candidate constraints too.
exact = ConstraintSolver(algorithm="exact_cover")
assert exact.solve(state).to_string() == answer.to_string()
```

The facade's `analyze` results share `solutions`, `solution_count`, `exhaustive`, `first_solution`, `is_unique`, `is_unsatisfiable` and `has_multiple_solutions`. Their **statistics classes differ** because their search engines count different events.

## Domain propagation

Every cell has a domain of candidate digits, represented as a 9-bit mask. Fixed clues are singleton domains. Propagation repeatedly:

1. Removes each singleton's digit from all cells sharing its row, column, or box (peer inequality). A newly singleton domain is queued for propagation (a *naked single*).
2. Checks each row, column, and box for every digit. If a digit has no position, the state is contradictory. If it has only one position, that cell is forced (a *hidden single*).
3. Stops when no new singleton arises; if cells remain ambiguous, search branches and propagates again.

The solver copies its domain list before every speculative branch. It never mutates its input.

## Exact-cover formulation and Algorithm X

Standard Sudoku is an **exact-cover** problem with **324 primary constraints**:

| Constraint class | Columns | Meaning |
| --- | ---: | --- |
| Cell occupancy | 81 | Exactly one digit per cell |
| Row-digit | 81 | Each digit appears once per row |
| Column-digit | 81 | Each digit appears once per column |
| Box-digit | 81 | Each digit appears once per 3x3 box |

Every potential placement `(row, column, digit)` corresponds to a candidate
row with exactly four `1` entries, one for each constraint class. A completely
empty Sudoku has 729 candidate rows. Fixed clues and previously eliminated
candidates restrict which rows are initially present in the matrix.

Algorithm X chooses the active constraint column with the fewest compatible
rows (Knuth's **S heuristic**); a zero-option column is a contradiction. Each
chosen row removes its four columns and all intersecting rows. Reversing the
operations restores the original search state for the next choice. This
implementation uses Python sets rather than the doubly-linked node structure
of Dancing Links (DLX), avoiding a separate dependency and keeping the code
simple to audit. It is still Algorithm X, not a propagation heuristic.

Tie-breaking is deterministic: minimum column ID, then ascending candidate
row ID. Search is exhaustive unless it reaches the requested solution cap.
When input is `CandidateState`, all existing eliminations are respected, but
**not re-verified**. The original `ReferenceSolver` remains the clue-only
correctness oracle. Algorithm X's minimum-column ordering is fixed; selecting
custom `variable_heuristic` or `value_heuristic` options with
`ConstraintSolver(algorithm="exact_cover")` raises `ValueError` rather than
silently ignoring them.

## Heuristics

`variable_heuristic`:

- `"first"`: choose the first unresolved cell in row-major order.
- `"mrv"` (default): choose the unresolved cell with the fewest remaining candidates; ties go row-major.
- `"mrv_degree"`: MRV first, then prefer the cell constraining the most unresolved peers; final ties go row-major.

`value_heuristic`:

- `"ascending"` (default): try candidate digits in ascending order.
- `"lcv"`: try the candidate currently appearing in the fewest other unresolved peer domains first (least constraining value), then ascending ties.

The heuristic choices affect search order, not which solutions are valid. With a limit of two, different choices can yield different *first* completions for a nonunique puzzle.

## Completeness, termination and counting

For all three backends, `analyze(limit=2)` searches for up to two distinct completed boards. `is_unique` is True only if the **entire search** finished with exactly one solution. A positive result that stops because of the cap has `exhaustive=False`; `limit=1` cannot prove uniqueness.

An unsatisfiable input (with locally valid clues or constrained candidate domains) yields zero solutions and `is_unsatisfiable=True`. Invalid board formats or conflicting initial clues still raise `ValueError` through `SudokuBoard` validation.

The solver has no runtime timeout or node cap yet; exact solution counting for pathological inputs may consume considerable CPU. This backend is **not wired into synchronous application requests**.

## Statistics

- `nodes`: DFS states entered (including dead ends and solutions).
- `decisions`: speculative candidate assignments attempted, excluding forced assignments.
- `propagations`: domain transitions from multiple candidates to a singleton via peer/domain-unit deduction, including transitions in failed branches and excluding initial clues and branch decisions.
- `backtracks`: attempted speculative branches that produced no new solution.
- `max_depth`: maximum number of nested speculative assignments.
- `elapsed_seconds`: wall-clock runtime of propagation search, starting after input-to-domain conversion.

For `ExactCoverStatistics`: `nodes` counts recursive states, `row_selections`
counts selected candidate-placement rows, `decisions` counts choices from
columns with multiple options, `forced_selections` counts choices from columns
with one option, `dead_ends` counts zero-option columns, `backtracks` counts
selections with no solution in their subtree, and `max_depth` is at most 81.
Its `elapsed_seconds` includes sparse matrix construction and search, but not
parsing the original input.

Unlike the reference engine, propagation typically resolves an easy puzzle at **one DFS node**; therefore, raw node counts between the two algorithms are not directly comparable. Timings are affected by machine, run order, and Python interpreter.

Run regression tests from the project root:

```bash
PYTHONPATH=src python -m pytest -q tests/solvers/constraint
```

Run repeatable small-scale benchmarks:

```bash
PYTHONPATH=src python scripts/benchmark_constraint.py --repeats 5
```

The benchmark prints CSV with median **external wall-clock timings** (including input conversion) for all three backends and propagation heuristics, and validates solution classifications against the independent reference solver. Node counts differ in meaning between backends; compare runtimes for performance, not raw nodes. These are small smoke-test benchmarks, not a representative large-dataset performance claim.

## Future hybrid mode (not yet part of the application)

A future coordinator can run `LogicalSolver().solve(board)`, return its trace when solved, and on `SolveStatus.STUCK` pass `logical_result.state` **directly** to `PropagationSolver().analyze(...)` or `ExactCoverSolver().analyze(...)`. Do not recreate a plain SudokuBoard from the partially solved grid: that would silently restore candidates that the logical solver already eliminated. Distinguish algorithmic choices/branches from verified human deductions in the user-facing history. Explicitly decide how `STEP_LIMIT`, contradictions and nonunique puzzles should be reported before UI integration.
