# Hybrid Sudoku coordinator (backend only)

The `sudoku.solvers.hybrid` package coordinates the existing verified human-logic
solver with one of four independent mathematical solvers. It changes **no UI,
web endpoints, session/replay code, logical techniques, or constraint backends**.

The three supported modes are:

| `mode` | Operation | Possible outcomes |
| --- | --- | --- |
| `"logical"` | Apply verified human deductions only | `solved`, `stuck`, `step_limit` |
| `"constraint"` | Skip human deductions and solve by the chosen mathematical backend | `solved`, `unsatisfiable` |
| `"hybrid"` | Use human deductions first, fall back on `stuck` | `solved`, `unsatisfiable`, `step_limit` |

The default backend is `"propagation"`. The other options are `"reference"`,
`"exact_cover"`, and `"integer_programming"`. Only the last one requires
optional SciPy (`pip install -e ".[milp]"`). MRV, degree, and LCV options apply
only to propagation and follow the same validation rules as `ConstraintSolver`.

## Example usage

```python
from sudoku.solvers.hybrid import HybridSolver

puzzle = "530070000600195000098000060800060003400803001700020006060000280000419005000080079"

# Default: try every registered logical technique, then use propagation if stuck.
result = HybridSolver(mode="hybrid", constraint_algorithm="propagation").solve(puzzle)
print(result.status.value, result.completed_by, result.used_fallback)
print(result.first_solution)

# Human deductions only, including partial progress and a replayable history.
logical = HybridSolver(mode="logical").solve(puzzle)
print(logical.status.value, len(logical.steps))

# Direct mathematical solving, without invoking any human techniques.
exact = HybridSolver(mode="constraint", constraint_algorithm="exact_cover")
mathematical = exact.solve(puzzle, solution_limit=2)
print(mathematical.solution_count, mathematical.is_unique)

# Configurable techniques and heuristics; cap logical steps and intentionally
# fall back even when logical solving has not yet exhausted its options.
from sudoku.solvers.logical.solver import LogicalSolver
from sudoku.solvers.logical.singles import NakedSingle

solver = HybridSolver(
    mode="hybrid",
    logical_solver=LogicalSolver((NakedSingle(),)),
    constraint_algorithm="propagation",
    variable_heuristic="mrv_degree",
    value_heuristic="lcv",
    fallback_on_step_limit=True,
)
result = solver.solve(puzzle, max_logical_steps=10)
```

## Handoff and provenance

- `result.logical_result` contains the original `LogicalSolver` result, including
  verified `SolveStep` objects; `result.steps` is a convenience alias for those
  **human-only** deductions. An algorithmic completion never produces invented
  human-technique steps.
- `result.handoff_state` snapshots the complete `CandidateState` when human
  deduction stops and fallback begins. It is `None` if no fallback occurred.
  Candidate eliminations and placed values are both preserved.
- `result.constraint_result` contains the selected backend's original result,
  including search statistics and capped solution counts. It is `None` unless a
  mathematical search actually ran.
- `result.completed_by` is `"logical"` or `"constraint"` for a solved board,
  otherwise `None`. `result.used_fallback` is True only if *both* phases ran.
- `result.state` is the final candidate-state snapshot. After mathematical
  completion, the chosen solution is applied to a copy of the handoff state,
  preserving original givens; it is **not** added to the logical deduction
  history. `result.first_solution` returns a board copy when solved, else `None`.
- `result.solution_count` and `result.is_unique` are `None` when constraint
  search was not run, because logical completion alone does not prove uniqueness.
  When search ran, its `is_unique=False` means *not proven unique*, not
  necessarily multiple solutions: a `solution_limit=1` search is truncated.
  Use `solution_limit=2` (the default) to distinguish one, zero, or multiple
  solutions via `constraint_result`.

**Reference backend handoff:** The reference facade does not accept
`CandidateState` directly. Instead, the coordinator translates every current
candidate exclusion into explicit `forbidden=(row, column, digit)` assumptions
for `ReferenceSolver.analyze()`. It neither alters the reference implementation
nor forgets the eliminated candidates. The reference solver treats these as
input constraints, **not independent proofs of their correctness**.

## Stopping, errors, and contradictions

- The default hybrid fallback occurs **only on `SolveStatus.STUCK`**. A
  `STEP_LIMIT` means the caller stopped the logical pass early and is returned
  without invoking constraint search. Explicitly set
  `fallback_on_step_limit=True` to permit an early handoff.
- If the logical solver finishes, the constraint backend is not called.
- `HybridStatus.UNSATISFIABLE` requires an exact backend's infeasibility proof;
  local contradictions may instead be raised earlier by `SudokuBoard` or
  `CandidateState`, and verified human deductions may raise
  `CandidateContradiction` as before. The coordinator does **not** silently
  suppress those exceptions or equate a step cap with unsatisfiability.
- The input board or candidate state is copied. Mathematical search respects
  previously recorded eliminations, but does not independently prove them.
- Bad solver configuration, malformed inputs, and invalid limits raise
  `ValueError` or `TypeError`. Errors from the MILP backend (including resource
  or numerical failures) propagate instead of being treated as infeasibility.
- In `"constraint"` mode, supplying `max_logical_steps` is an error rather than
  silently ignoring it.

## Running the tests

From the repository root:

```bash
PYTHONPATH=src python -m pytest -q tests/solvers/hybrid tests/solvers/constraint
```

The hybrid suite covers all four backends, a genuine human-logic `STUCK`
state, a real `Pointing` elimination preserved through fallback, successful
logical-only completion, step caps and opt-in fallback, multiple solutions,
unsatisfiable puzzles, original-given preservation, and input immutability.
