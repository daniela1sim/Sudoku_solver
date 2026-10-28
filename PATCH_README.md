# Reference solver patch for daniela1sim/Sudoku_solver

Based on public GitHub `main` inspected on 2026-10-28 (head `ff4fe450925650e71d0ce38bcd2194d295c0d84d`).

**Apply to your existing GitHub checkout**: extract this ZIP at repository root.
It only ADDS files; it does not replace your updated UI, `solver.py`,
`verification.py`, README, or any existing logical technique.

New files:

- `src/sudoku/solvers/constraint/__init__.py`
- `src/sudoku/solvers/constraint/reference.py`
- `tests/solvers/constraint/test_reference.py`
- `tests/solvers/constraint/test_reference_oracle.py`
- `docs/reference_solver.md`

Run using your existing setup (Windows PowerShell):

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q tests/solvers/constraint
python -m pytest -q
```

The new solver is a correctness oracle only, not a replacement for the
human-style solver or the interactive replay/hints experience.

Validation performed against the prior logical-core snapshot with the same
public `SudokuBoard`/`LogicalSolver` APIs and the finned-fish optimization:
**464 tests passed** (426 existing + 38 new). The three UI integration tests
in the current GitHub repository should also be rerun locally because the
project's newer UI files are intentionally not part of this patch.
