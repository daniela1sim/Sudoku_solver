# Generated Sudoku test dataset

This directory contains **144 distinct 9×9 Sudoku puzzles**, with **36 puzzles in each of four measured technique tiers**. Every puzzle has **exactly one solution**, verified using the project's independent `ReferenceSolver` with a two-solution limit. No third-party puzzle site or downloaded corpus was used.

## Files

- `puzzles.jsonl`: One JSON object per line, suitable for streaming, testing, and benchmarking.
- `../scripts/generate_puzzles.py`: Seeded puzzle generator, uniqueness verification, and technique-based difficulty classification.
- `../scripts/benchmark_dataset.py`: Benchmarks these fixtures with the current solver backends; verifies the solved grids.
- `../tests/data/test_puzzle_dataset.py`: Dataset checks, independent backend comparisons, hybrid handoff checks, and seeded reproducibility.

## Difficulty is operational, not universal

A label is determined by the **least powerful of three specific verified technique sets that solves the puzzle** (the logical solver tries deductions in its defined priority order):

| Label | Meaning | Count |
| --- | --- | ---: |
| `easy` | Naked/hidden singles alone solve it | 36 |
| `medium` | Singles do not suffice; singles + locked candidates + pairs/triples solve it | 36 |
| `hard` | Basic set gets stuck; adding X-Wing, Skyscraper, Two-String Kite, XY-Wing, Simple Coloring, and X-Chain solves it | 36 |
| `expert` | Even that selected advanced set gets stuck | 36 |

**Important:** `expert` does **not** imply that the project's *full* human-logic solver gets stuck, or that guessing is mathematically required. Its full technique registry contains additional methods. This classification is a **reproducible project-specific test criterion**, not an external human difficulty rating. Number of givens is recorded separately but is **not** used to assign the label. Technique priority and implemented methods can change over time; regenerate and revalidate the classifications if that happens.

## Record schema

Each line has:

```json
{
  "id": "HARD-001",
  "difficulty": "hard",
  "puzzle": "<81 digits, 0 means blank>",
  "solution": "<81 filled digits>",
  "givens": 27,
  "logical_profile": {
    "singles": {"status": "stuck", "steps": 12},
    "basic": {"status": "stuck", "steps": 20},
    "advanced": {"status": "solved", "steps": 60}
  },
  "reference_nodes": 123,
  "reference_branches": 122
}
```

The example numbers above are **illustrative**, not the metadata of a particular real puzzle. Missing later `logical_profile` keys mean a less powerful technique set already solved the puzzle, so later sets were not run. `reference_nodes` and `reference_branches` describe the generator's reference-solver `analyze(limit=2)` run; they are **not** a human difficulty score. `solution` enables exact equality checks across all backends.

## Reproducing and checking the dataset

From the project root, with the package installed (`pip install -e '.[dev]'`) or `PYTHONPATH=src` set:

```bash
python scripts/generate_puzzles.py --seed 20261029 --count-per-tier 36
python -m pytest tests/data/test_puzzle_dataset.py -q
python scripts/benchmark_dataset.py --per-tier 5 --repeats 3 > benchmark.csv
```

The generator performs a randomized MRV fill of a complete grid, then removes clues one at a time, **retaining a deletion only if uniqueness remains**. Its RNG is seeded, and puzzles are accepted only after reference verification and logical classification. It may take hundreds of generation attempts to reach the balanced target. `--max-attempts` bounds the search and fails explicitly if insufficient puzzles are found. Running with the same seed, settings, environment, and technique definitions produces the same output (byte-for-byte).

To benchmark the complete corpus, pass `--per-tier 0`. The default benchmark runs three dependency-free mathematical backends. Add `--algorithms integer_programming` for SciPy/HiGHS (requires `pip install -e '.[milp]'`) or `--algorithms hybrid --hybrid-backend propagation` for the full human-logic + fallback pipeline. **The hybrid benchmark may be considerably slower** on challenging fixtures. CSV `median_search_nodes` values across different algorithms have different definitions and should not be compared directly. Time measurements depend on hardware and execution conditions.

For the default seed and settings, the committed `puzzles.jsonl` file has SHA-256 `3e8524dd749b1257cdbce897a3a20fa2f0ea260f8e01f3c76af9799c078a1a4c`, checked by regenerating the entire file.

This dataset is generated, not a benchmark certified against a third-party puzzle-rating scale. It is appropriate for correctness, regression, and comparative-performance tests; avoid treating the tier labels as universal Sudoku difficulty standards.
