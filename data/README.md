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

For the default seed and settings, the **unrated generator output** has SHA-256 `3e8524dd749b1257cdbce897a3a20fa2f0ea260f8e01f3c76af9799c078a1a4c`, checked by regenerating the file. The separately enriched `puzzles.jsonl` has additional rating fields and therefore a different hash.

This dataset is generated, not a benchmark certified against a third-party puzzle-rating scale. It is appropriate for correctness, regression, and comparative-performance tests; avoid treating the tier labels as universal Sudoku difficulty standards.

## Local logical difficulty ratings

The corpus also stores a `rating` object generated with the project's
**existing** `src/sudoku/solvers/logical/rating.py` calculator. This is a
solve-path estimate inspired by Sudoku Explainer, **not an official SE rating**.
Unlike the operational `difficulty` tier (based on restricted technique sets),
the numerical rating uses the **full default `LogicalSolver`**, with uniqueness
techniques disabled. Each record retains its original `id`, `puzzle`, `solution`,
`givens`, `difficulty`, `logical_profile`, and reference search metrics.

`rating` contains:

- `method`: `local-technique-v1`, with `config` identifying default techniques,
  `allow_uniqueness=false`, and any logical step limit.
- `status`: `complete` only if all cells were filled using verified human
  deductions; `incomplete` if stuck; `step_limit` if a configured step bound
  was reached; `timeout` if the external runtime bound was reached. Other
  diagnostic states can include `unsupported` and `error`.
- `score`: the **maximum** step weight across a *complete* logical replay;
  `null` otherwise. Do **not** sort `null` as 11.9 or treat it as proof that
  guessing is necessary.
- `observed_peak`: highest technique weight seen before a normal incomplete
  solve; it is descriptive, not a difficulty lower bound. Null on timeout.
- `hardest_technique`, `logical_status`, `steps`, `placements`,
  `eliminations`, and `technique_counts` for analysis.

For example, a puzzle in the restricted-set `expert` tier may nevertheless be
fully solved by the default logical engine and receive a final numerical
rating. This reflects the difference in enabled techniques, not a conflict.

Recreate ratings without regenerating puzzles:

```bash
PYTHONPATH=src python scripts/rate_puzzles.py
# Force recalculation if method weights or logical technique definitions change:
PYTHONPATH=src python scripts/rate_puzzles.py --force --timeout-seconds 20
# Work on a copy instead of rewriting the committed data file:
PYTHONPATH=src python scripts/rate_puzzles.py --input data/puzzles.jsonl --output data/rated.jsonl
# Validate the enriched metadata:
PYTHONPATH=src python -m pytest tests/data/test_puzzle_ratings.py -q
```

Each puzzle is processed in its own subprocess, allowing a per-puzzle timeout
on Windows and Linux. Completed records are saved atomically after each puzzle;
re-running skips already rated entries with a matching method/configuration.
Use `--force` to retry timeouts or refresh older scores after code changes.
The timeout does not itself measure puzzle difficulty, and differing timeouts
may affect the fraction of fully rated puzzles. Running the seeded generator
alone produces the original unrated corpus; running `rate_puzzles.py` afterward
adds the rating fields. Exact scored records also depend on the version of the
logical technique implementation, not just the generator's seed.

`benchmark_dataset.py` includes `rating_status`, `rating_score`, and
`hardest_technique` columns so computational costs can be analyzed against
human-logic difficulty. Records lacking ratings remain usable and show
`not_rated` in the benchmark.

For the committed rated dataset (default full logical solver, 5-second
per-puzzle timeout), **143 puzzles have completed ratings** and one,
`EXPERT-017`, has `status=incomplete` with `score=null` and an observed
peak of 8.0 (Grouped AIC). These are empirical outcomes from the current
solver version, not fixed mathematical classifications. The rated file has
SHA-256 `66083d254a77c28a99b0d50c1481f0afb4b8df0764a00f19243ad334b6fe5176`.
