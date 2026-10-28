# Wing verification refactor — add to current Sudoku_solver repository

## Summary

XY-Wing, XYZ-Wing, and W-Wing now use direct **witness-directed verification**: the verifier checks the supplied premise cells, their current candidate sets, Sudoku peer geometry, actual W-Wing conjugate links, and every elimination. It no longer imports or reruns `_wing_patterns` from the detector. Discovery algorithms and UI APIs are unchanged.

The replacement `verification.py` also **retains the prior independent Fish verification refactor**. Do not replace it with an older file.

## Installation

### Option A: quick 3-file ZIP

Extract the three files into `src/sudoku/solvers/logical/`:

- `verification.py` — replaces existing verifier, includes Fish and Wing refactors.
- `fish_proofs.py` — previous Fish proof helper (provided to make this ZIP self-contained).
- `wing_proofs.py` — new Wing proof helper.

### Option B: repository-structured patch ZIP

Extract at the repository root, preserving directories. The patch also adds
`tests/solvers/logical/test_wing_proof_independence.py` and this document.

## Technique-specific checks

- **XY-Wing**: exactly bivalue pivot `{x,y}` and two bivalue wings `{x,z}` and `{y,z}`, wings each see pivot; `z` elimination targets see both wings.
- **XYZ-Wing**: exactly trivalue pivot `{x,y,z}`, wings `{x,z}` and `{y,z}` each see pivot; `z` targets see all three pattern cells.
- **W-Wing**: two nonseeing bivalue wings `{x,z}`; an exact conjugate pair for `x` in a row/column/box with each endpoint seeing its corresponding wing; `z` targets see both bivalue wings. A link endpoint may be a valid target if it sees both wings and still contains `z`.

The verifier rejects absent/stale target candidates, unrelated digits, invalid geometry, malformed premises, and placements. It accepts justified subsets of a detector's eliminations. Deductions do not mutate state.

## Testing

```powershell
$env:PYTHONPATH = 'src'
python -m pytest -q
```

The standalone tests monkeypatch Wing discovery helpers to raise during validation; the verifier still succeeds. They also exercise falsified witness fields, W-Wing column/box conjugacy, and independently verify effects from an actual uniquely solvable Sudoku puzzle when the `constraint` reference solver package is installed.

The baseline for the packaged verifier is the previous independent Fish-verification patch, and `wings.py` was checked against the GitHub repository's `main` version. The patch does not modify the UI, detection functions, solver priority order, or public deduction format.
