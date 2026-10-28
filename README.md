# Intelligent Sudoku Solver

An extensible Python project for solving Sudoku puzzles with **human-style logical deductions**, **mathematical constraint-solving algorithms**, and eventually **machine-learning-assisted strategies**.

The central goal is not merely to produce a completed grid, but to make the solving process **correct, traceable, and explainable**: every logical placement or candidate elimination should be supported by an explicit justification.

> **Project status:** Active development. The explainable logical-solving engine, interactive hints/replay application, independent exact reference solver, and experimental local image importer are implemented. Broader image-recognition coverage, additional constraint-solving methods, and ML/LLM experiments remain planned.

## Project goals

1. **Explainable logical solving:** Implement human Sudoku techniques, from singles and subsets to advanced patterns and inference chains. Record the premises and consequences of each deduction.
2. **Constraint solving:** Implement and compare backtracking, constraint propagation, search heuristics, and exact-cover methods.
3. **ML/LLM experiments:** Investigate whether learned heuristics or LLM-assisted technique selection can improve existing solvers without compromising correctness.
4. **Puzzle input and visualization:** Support structured grids, reviewed image imports, and interactive step-by-step explanations; improve recognition across real-world puzzle images.

## Development roadmap

### Phase 1 — Human-style logical solver

- [x] Define a `SudokuBoard` representation and validate puzzle constraints.
- [x] Track candidate sets for empty cells.
- [x] Design immutable, structured `Deduction` records for placements, eliminations, and supporting premises.
- [x] Implement Naked Singles and Hidden Singles.
- [x] Implement Locked Candidates and Naked/Hidden Subsets (pairs, triples, quads).
- [x] Implement Skyscraper, 2-String Kite, XY/XYZ/W-Wing, advanced rectangles, and finned fish.
- [x] Add Simple Coloring and Remote Pairs.
- [x] Add bounded, single-digit X-Chains (4-, 6-, and 8-cell chains).
- [x] Add bounded XY-Chains over bivalue cells.
- [x] Add ALS-XZ and strict Sue de Coq (two-sector disjoint subsets).
- [x] Add bounded ALS-Chains with independent RCC and elimination verification.
- [x] Add bounded, individual-candidate Alternating Inference Chains (AICs), including continuous and discontinuous loops.
- [x] Add grouped-candidate AICs (box-line groups), including independently verified open chains and loops.
- [x] Extend the candidate inference graph with ALS-digit propositions (ALS-AICs), with independent verification.
- [ ] Unify ordinary, grouped, and ALS-AIC nodes in one inference graph and optimize discovery.
- [x] Implement generalized basic fish (X-Wing, Swordfish, Jellyfish).
- [x] Preserve a reproducible solving history with explanatory deduction premises.
- [x] Add unit and integration tests for techniques, contradictions, and invalid inputs.

### Phase 2 — Mathematical constraint solvers

- [x] Implement an independent reference solver using recursive backtracking.
- [x] Add Minimum Remaining Values (MRV) search and row/column/box bitmasks.
- [ ] Add forward checking and compare search heuristics.
- [ ] Implement Algorithm X / exact cover.
- [ ] Compare results with an established solver (e.g., Z3).
- [ ] Benchmark solve time, search nodes, backtracks, and memory usage.
- [ ] Evaluate combinations of logical preprocessing and search.

### Phase 3 — ML and LLM experiments

- [ ] Establish benchmark datasets and reproducible evaluation procedures.
- [ ] Test model-guided search or technique selection against conventional heuristics.
- [ ] Explore structured explanations generated from verified deductions.
- [ ] Measure correctness, computational cost, and performance gains.

### Image input and interactive application

- [x] Add an experimental printed-puzzle image importer with editable review.
- [ ] Benchmark image recognition on real photos and broaden font/handwriting support.
- [x] Build an interactive application for replaying deductions and requesting hints.
- [x] Allow users to choose which logical techniques the solver may use.

### Next tasks

These are proposed follow-up tasks, not capabilities of the current application.

**Image recognition — immediate priority**

- [ ] Build a labeled image collection spanning screenshots, printed photos, fonts, colored grids, compression, shadows, and perspective distortion. Record source/redistribution permission for each fixture.
- [ ] Report exact-grid accuracy, digit accuracy, missed clues, and false digits in empty cells separately; retain every reported failure as a regression case.
- [ ] Add manual crop, rotation, and corner adjustment when automatic grid detection fails.
- [ ] Compare the template recognizer with a local OCR or trained digit model using a held-out image set; package fonts or model assets for reproducible results across operating systems.
- [ ] Improve uncertain-cell review with enlarged cell crops and alternative readings. Keep corrections explicit rather than silently using Sudoku constraints to change clues.
- [ ] Detect candidate notes and handwriting, and either support them with dedicated recognition or clearly flag unsupported input.
- [ ] Add automated browser coverage for upload, correction, review confirmation, and starting a replay from an imported puzzle.

**Solver and application**

- [ ] Offer an explicit solvability/uniqueness check through `ReferenceSolver`, distinct from the existing uniqueness assumption checkbox.
- [ ] Save and restore puzzle drafts, technique choices, and replay history across page refreshes.
- [ ] Profile advanced technique searches and add reproducible performance benchmarks before increasing search bounds.
- [ ] Extend independent oracle checks and proof-verification tests when adding or changing techniques.

**Repository maintenance**

- [ ] Move the existing `src/sudoku/solvers/logical/test_fish_proof_independence.py` into the test tree after reviewing it; the default pytest configuration currently discovers only `tests/`.
- [ ] Add continuous integration for core tests without vision dependencies and image tests with the optional packages, including Windows/Linux coverage.
- [ ] Choose a license and add `LICENSE`; review distribution rights for image fixtures and any bundled recognition assets.
- [ ] Move the legacy patch ZIP out of the Python source package and document whether it should be retained as a release artifact.

## Independent reference solver

The `sudoku.solvers.constraint` package provides an exact solver for checking
solvability, uniqueness, and the truth of logical deductions. It uses deterministic
backtracking with MRV and bitmasks, independently of the logical techniques,
candidate tracker, and deduction verifier. It has no additional runtime dependencies.

```python
from sudoku.core.board import SudokuBoard
from sudoku.solvers.constraint import ReferenceSolver

puzzle = SudokuBoard.from_string(
    "530070000600195000098000060800060003400803001"
    "700020006060000280000419005000080079"
)
oracle = ReferenceSolver()
solution = oracle.solve(puzzle)  # SudokuBoard, or None if unsatisfiable
analysis = oracle.analyze(puzzle)  # Search for up to two solutions
print(analysis.is_unique)
print(analysis.has_multiple_solutions)
print(analysis.is_unsatisfiable)
print(analysis.statistics)

# Check a deduction against the original clues (zero-based coordinates).
assert oracle.forces_placement(puzzle, 0, 2, 4)
assert oracle.proves_elimination(puzzle, 0, 2, 1)
```

Solution counts are capped by the requested limit. Finding a single solution
with `limit=1` does not establish uniqueness. Deduction checks require the
original puzzle to be satisfiable, so contradictions do not prove arbitrary
moves. The oracle remains a library and testing facility; the interactive app
continues to use the selected logical techniques for hints and replay.

See [the reference solver documentation](docs/reference_solver.md) for the full
API, assumptions, audit examples, and performance considerations. The added files
are `src/sudoku/solvers/constraint/`, `tests/solvers/constraint/`, and
`docs/reference_solver.md`; [PATCH_README.md](PATCH_README.md) preserves the supplied
patch's application notes and its original validation context.

Run its tests from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q tests/solvers/constraint
```

## Interactive deduction studio

### Import a printed puzzle image (experimental)

Install the optional image packages from the repository root:

```powershell
python -m pip install ".[vision]"
$env:PYTHONPATH = "src"
python -m sudoku.app
```

In puzzle setup, expand **Import a puzzle image**, choose a PNG/JPEG/WebP,
and click **Read image**. The importer detects the grid, corrects perspective,
and reads printed digits using local glyph templates. Compare the editable grid
with the straightened image, correct any mistakes, and check **I reviewed the
grid against the image** before starting. Amber cells indicate uncertain readings
or duplicate clues. Recognition does not create a solving session or fill missing
clues using Sudoku constraints. Images stay local and are not saved by the server.

This first version targets upright, dark-on-light, clearly ruled printed grids
and screenshots. It is not a trained OCR model. Handwriting, candidate notes,
decorative fonts, heavy shadows, major rotation, and incomplete borders are not
supported reliably. Even unflagged digits and blank cells can be wrong; similarity
scores are not probabilities. Available system fonts affect template coverage.
Uploads are limited to 8 MiB and 16 megapixels. The ordinary solver still runs
without the optional dependencies.

Try [the generated perspective sample](docs/sample-puzzle.png) for a first import.

The implementation is isolated in `src/sudoku/vision/reader.py`; its public API
is `read_image(image_bytes)`, returning the draft puzzle, cell scores/review flags,
direct conflicts, and a straightened PNG preview. Regression tests cover generated
grids with perspective distortion and the supplied colored-grid screenshot in
`tests/vision/fixtures/colored-grid.png`, including resized and JPEG variants.
Narrow border remnants are filtered so grid-line slivers are not read as `1`s in
empty cells. These checks do not establish general real-photo accuracy, which
remains unmeasured.

### Launch and use the studio

Run the local browser application from the repository root (Python 3.10+):

```powershell
$env:PYTHONPATH = "src"
python -m sudoku.app
```

Open **http://127.0.0.1:8000**. To use another port, run
`python -m sudoku.app --port 8001`. Stop the server with Ctrl+C.
Manual entry, hints, and replay use only Python's standard library and the existing
solver. No frontend build is needed. Image import additionally requires the
optional `vision` packages shown above.

1. Enter clues by clicking grid cells and typing digits, or paste an 81-character
   string and click **Use string**. Whitespace is accepted; zeros and dots mean
   empty cells. The classic warm-up is preloaded on startup. Choose from six
   bundled puzzles in **Example puzzles**, then click **Load example** to load
   your selection. The collection includes the classic warm-up, Box by box,
   Fresh perspective, sparse singles practice, and two advanced examples.
   The advanced examples come from [Peter Norvig's top95 collection](https://norvig.com/top95.txt):
   puzzle 13 uses Skyscrapers, and puzzle 19 uses Empty Rectangles and a naked
   triple with the default solver. Both solve completely and require more than
   singles. **Clear grid** gives you
   a blank grid for custom entry. Puzzle data lives in the `examples` collection
   in `src/sudoku/app/static/app.js`.
2. Click **Start exploring** to prepare the full available replay automatically,
   while keeping the board at its initial position. Use **Give me a nudge** for a strategy question
   without revealing the technique, locations, or move. **Show where to look**
   names the technique and highlights its supporting cells. **Reveal the
   deduction** then shows the full explanation, placements, and eliminations.
   Each level requires a separate click and leaves the board unchanged.
   **Apply this deduction** appears only after the final reveal.
3. Use **Back**, **Next**, the replay slider, or a history entry to revisit exact
   saved states, including candidate eliminations. Deduction history shows only
   the moves up to the displayed position: it grows as you advance and shrinks
   when you go back, without listing future deductions. **Play** replays recorded moves
   automatically and stops at the latest recorded state. At the end, **Play**
   restarts recorded history. **Next step** revisits a recorded move; when no
   recorded move is ahead, it becomes **Next hint** and advances the hint levels
   without applying a move. The explicit **Apply this deduction** button advances
   the displayed board after revealing a hint. **Pause** stops after an in-flight
   replay step finishes. Replay generation stops when solved or when the logical
   solver has no further available move.
4. Toggle candidate notes and inspect the highlighted reasoning cells,
   placements, and eliminations. **Edit puzzle / start over** returns to the
   original clues and starts a fresh history when loaded again.

Uniqueness-based techniques are off by default. The optional uniqueness checkbox
is an assumption supplied by the user, not a uniqueness check. When the solver
finds no further deduction within its techniques and search bounds, the app says
so; that does not mean the puzzle is unsolvable.

Expand **Logical techniques** in puzzle setup to select individual techniques,
or use **Select all**, **Singles only**, or **Select none**. All ordinary
techniques are selected by default; uniqueness techniques remain unavailable
until the uniqueness assumption is enabled. The selection applies to both hints
and automatic replay, retaining the solver's usual technique priority. Selecting
none is allowed and leaves an unfinished puzzle with no available deductions.
Use **Edit puzzle / start over** to change the selection and rebuild the replay
from the original clues; this replaces the previous replay. Choices are kept
while editing in the same page and reset on refresh.

Sessions are held in server memory (up to 32 recently used sessions). Refreshing
the page starts a new workspace; restarting the server discards all sessions.
The server binds only to `127.0.0.1` and is intended for local use.

The application lives in `src/sudoku/app/`: `session.py` manages replay and hint
state, `__main__.py` serves the JSON API and bundled static files, and `static/`
contains the browser interface. It calls the same verified `LogicalSolver`
used by library clients.

## Current repository structure

The tree below reflects the current working directory. Package `__init__.py`
files and individual technique/test modules are condensed where indicated;
generated caches and Git internals are omitted.

```text
Sudoku_solver/
├── README.md
├── PATCH_README.md                 # Historical reference-solver patch notes
├── .gitignore
├── pyproject.toml
├── docs/
│   ├── reference_solver.md         # Exact solver API and correctness audits
│   └── sample-puzzle.png           # Generated perspective image to try
├── src/
│   └── sudoku/
│       ├── app/
│       │   ├── __main__.py         # Local HTTP server, JSON API, image upload
│       │   ├── session.py          # Replay and hint state
│       │   ├── techniques.py       # Selectable technique catalog
│       │   └── static/
│       │       ├── index.html
│       │       ├── app.js
│       │       └── style.css
│       ├── core/
│       │   ├── board.py            # Board representation and clue validation
│       │   ├── candidates.py       # Candidate tracking and state updates
│       │   └── deduction.py        # Structured deductions and premises
│       ├── solvers/
│       │   ├── constraint/
│       │   │   └── reference.py    # Independent MRV/bitmask exact solver
│       │   └── logical/
│       │       ├── base.py
│       │       ├── solver.py       # Technique orchestration
│       │       ├── verification.py # Deduction verification
│       │       ├── fish_proofs.py
│       │       ├── test_fish_proof_independence.py
│       │       └── …              # Singles, subsets, fish, wings, ALS, chains,
│       │                          # rectangles, coloring, and inference graphs
│       ├── vision/
│       │   └── reader.py          # Grid detection, perspective correction,
│       │                          # glyph templates, review/conflict metadata
│       └── sudoku-reference-solver-github-patch.zip  # Legacy patch archive
└── tests/
    ├── app/                       # Sessions, examples, techniques, HTTP API
    ├── core/                      # Candidates and deductions
    ├── solvers/
    │   ├── constraint/            # Reference solver and oracle checks
    │   └── logical/               # Techniques and deduction verification
    └── vision/
        ├── test_reader.py
        └── fixtures/
            └── colored-grid.png   # Regression: borders mistaken for digits
```

The checkout folder may have a different name (for example, `sudoku solver`).
`LICENSE`, `data/`, `benchmarks/`, `ml/`, and `solvers/hybrid/` do not yet exist.
The six example puzzle strings currently live in `app/static/app.js`.
Board validation lives in `core/board.py`; there is no separate `validator.py`.

The image importer returns a draft to the browser for review. Once accepted,
the draft enters the same `ReplaySession` and logical-solving flow as manual
input. The exact reference solver is currently a separate library/testing tool.

## Design principles

- **Correctness first:** Never apply an unsupported elimination or placement. Validate the final grid independently.
- **Separate discovery from mutation:** Techniques *propose* deductions; a central solver checks and applies them.
- **Structured reasoning:** A deduction stores the technique, relevant cells/candidates, premises, and effects independently of its textual explanation.
- **Shared core:** Logical, mathematical, and learned solvers use compatible puzzle representations.
- **Testability:** Each technique and algorithm has focused tests and regression cases.
- **Reproducibility:** Compare approaches on the same puzzles and report clearly defined metrics.

## Representation conventions

- Classic **9 × 9 Sudoku**, with digits `1` through `9`.
- Empty cells are represented by `0`.
- Internal cell coordinates are **zero-based** `(row, column)` pairs.
- Explanations use familiar **one-based** notation (for example, `R4C6`).
- Candidate eliminations must persist in the logical solver's state; they should not be lost by recomputing candidates solely from placed digits.

## Example puzzle format

A puzzle can be represented as a list of nine rows:

```python
puzzle = [
    [5, 3, 0, 0, 7, 0, 0, 0, 0],
    [6, 0, 0, 1, 9, 5, 0, 0, 0],
    [0, 9, 8, 0, 0, 0, 0, 6, 0],
    [8, 0, 0, 0, 6, 0, 0, 0, 3],
    [4, 0, 0, 8, 0, 3, 0, 0, 1],
    [7, 0, 0, 0, 2, 0, 0, 0, 6],
    [0, 6, 0, 0, 0, 0, 2, 8, 0],
    [0, 0, 0, 4, 1, 9, 0, 0, 5],
    [0, 0, 0, 0, 8, 0, 0, 7, 9],
]
```

Construct this grid with `SudokuBoard(puzzle)`, or use
`SudokuBoard.from_string(...)` for 81-character input. The reference solver API
is documented above and in `docs/reference_solver.md`; the browser entry point
is `python -m sudoku.app`. Examples for individual logical techniques follow below.

## Testing and benchmarks

Run the tests from the repository root:

```powershell
python -m pip install -e ".[dev,vision]"
$env:PYTHONPATH = "src"
python -m pytest -q
```

Tests cover candidate updates, logical techniques, deduction verification,
hint previews, replay state restoration, technique selection, the local HTTP API,
reference-solver solution counting and assumptions, and independent audits of
logical deductions against original clues, image recognition, blank-cell handling,
grid-border filtering, and invalid image uploads. Use `.[dev]` instead if only
the core application is needed; vision tests skip when their dependencies are
unavailable. To run just the importer and upload API checks:

```powershell
python -m pytest -q tests/vision tests/app/test_server.py
```

The HTTP integration tests need permission to connect to temporary localhost
servers. The default test discovery root is `tests/`, as configured in
`pyproject.toml`; the fish-proof test currently under `src/` is not included.
Benchmarks
remain planned and will distinguish **human-style difficulty** from
**algorithmic search complexity**, which need not correlate.

## Contributing

Add focused regression cases for bug fixes, keep deduction discovery separate
from verification, and run the relevant tests before submitting changes.
Image-recognition changes should check both printed clues and empty cells, and
must preserve the review step. Include expected puzzle strings and fixture
provenance when adding image cases. More detailed contribution guidelines remain
a future task.

## License

A license will be selected and included in `LICENSE` before public distribution.


## Locked Candidates and Disjoint Groups

The logical solver supports Pointing and Claiming by default. `DisjointGroups()` is an optional, standard-Sudoku technique giving complementary locked-set explanations for naked subsets, and does **not** implement the extra constraints of the Disjoint Groups Sudoku variant.

Run tests with `python -m pytest tests/ -v` after `pip install -e ".[dev]"`.

## Basic fish patterns

`src/sudoku/solvers/logical/fish.py` provides `BasicFish(size=2|3|4)` and convenient `XWing`, `Swordfish`, and `Jellyfish` classes. It detects row- and column-based basic fish, proposes eliminations with structured premises, and delegates independent validation to `DeductionVerifier`. The default `LogicalSolver` runs them after singles, locked candidates, and subsets. Finned fish variants are implemented separately in `finned_fish.py`; complex Franken and Mutant Fish are not supported.


### Short strong-link chains

The logical solver also supports **Skyscraper**, **2-String Kite**, and
**Crane** in `src/sudoku/solvers/logical/strong_links.py`.
All three use a four-candidate alternating chain
`tail A == connector A -- connector B == tail B` for one digit.
`==` represents a conjugate (exactly-two-candidate) pair in a row, column,
or box; `--` represents two different cells that see each other.
At least one tail contains the digit, so it can be eliminated from cells
that see both tails.

- **Skyscraper:** parallel row (or column) strong links; perpendicular weak link.
- **2-String Kite:** row and column strong links; box weak link.
- **Crane:** box and row/column strong links; row/column weak link.

The verifier reconstructs the chain from the live candidate state and checks
each proposed elimination. `test_strong_links.py` contains focused tests.

### Wing techniques (implemented)

The logical solver also supports **XY-Wing**, **XYZ-Wing**, and **W-Wing**
(`src/sudoku/solvers/logical/wings.py`). Each produces structured candidate
eliminations, which are checked by `DeductionVerifier` before execution:

- **XY-Wing:** a bivalue pivot `{x,y}` sees two bivalue wings `{x,z}` and
  `{y,z}`; `z` is removed from common peers of the wings.
- **XYZ-Wing:** a trivalue pivot `{x,y,z}` sees two bivalue wings `{x,z}` and
  `{y,z}`; `z` is removed only from cells seeing all three pattern cells.
- **W-Wing:** two separated bivalue cells `{x,y}` are linked by a conjugate
  pair for `x`; `y` is removed from cells seeing both bivalue cells.

These techniques are appended to the default solver's priority order after
Skyscraper, 2-String Kite and Crane.

### Advanced rectangle and finned-fish techniques

- **Empty Rectangle** (`rectangles.py`): uses a row/column cross of candidates
  inside a box and an external conjugate link to prove an elimination by
  contradiction. It does **not** assume a unique solution.
- **Finned X-Wing** (`finned_fish.py`): handles both row and column orientations;
  all fins must lie in one of the fin-line corner boxes. The target must lie
  in that box and in the relevant cover column/row.
- **Unique Rectangle Type 1** (`rectangles.py`): avoids a deadly rectangle of
  two identical bivalue pairs. **This method requires the assumption of
  exactly one solution.** It is deliberately excluded from the default solver.

```python
from sudoku.solvers.logical.solver import LogicalSolver

standard_solver = LogicalSolver()  # No uniqueness assumptions
unique_solver = LogicalSolver(allow_uniqueness=True)  # Only if uniqueness is known
```

All deductions are verified against the current candidate state before
application. Explanatory premise text is not a formal proof certificate.


### Unique Rectangle Types 1–6 (opt-in)

`UniqueRectangleType1` through `UniqueRectangleType6` are implemented in
`src/sudoku/solvers/logical/rectangles.py`. All six require the **external assumption that the initial puzzle has exactly
one solution**. This is not established by the logical solver.

- **Type 1:** Three bivalue floor corners; remove the deadly pair from the fourth.
- **Type 2:** Two floors and two roofs with a matching single extra digit;
  remove the extra from cells seeing both roofs.
- **Type 3:** Treat the union of roof extras as a virtual cell in a naked
  subset with other cells sharing a unit; remove those digits outside the group.
- **Type 4:** When one deadly digit is conjugate between the two roof cells
  in a common unit, eliminate the other deadly digit from the roofs.
- **Type 5 (HoDoKu convention):** A single extra digit appears in two diagonal
  corners or three corners; at least one of those guardians must be true.
  Eliminate it from any cell seeing every guardian.
- **Type 6 (HoDoKu convention):** The two diagonal floor cells are bivalue;
  one deadly digit appears only in the four corners across both defining rows
  and columns. Eliminate it from the two diagonal roofs.

```python
from sudoku.solvers.logical.solver import LogicalSolver
solver = LogicalSolver(allow_uniqueness=True)  # only for known unique puzzles
```

The default solver does not use uniqueness-based deductions.


### Hidden Unique Rectangle and generalized finned fish

- `HiddenUniqueRectangle` (`rectangles.py`) identifies a two-box deadly rectangle
  with a bivalue anchor and row/column conjugate links at the opposite corner.
  It **requires a proven or explicitly assumed unique solution** and is only
  enabled using `LogicalSolver(allow_uniqueness=True)`.
- `FinnedSwordfish` and `FinnedJellyfish` (`finned_fish.py`) examine 3 or 4
  base/cover lines, respectively, in both orientations. This implementation
  covers single-box fins on a single base line, including degenerate (sashimi)
  patterns where the same logical rule applies; it does not attempt complex fish.
- The verifier reconstructs candidate geometry before accepting eliminations.

To test: `python -m pytest tests/ -v` after `pip install -e ".[dev]"`.


### BUG+1 — Bivalue Universal Grave plus one (opt-in)

`BUGPlusOne` lives in `src/sudoku/solvers/logical/uniqueness.py`.
The implementation is regression-tested against a [HoDoKu BUG+1 worked example](https://hodoku.sourceforge.net/en/show_example.php?file=bug101&tech=BUG+%2B+1), in which R1C8 must be 6. That test fixture also has its unique completion checked independently.
It recognizes a late-game candidate state in which every unresolved cell is
bivalue except **one** trivalue cell. Importantly, the implementation does
**not** assume that this condition alone is enough: it independently checks
that removing one candidate from the trivalue cell would leave exactly **two**
positions for each missing digit in **every** row, column, and 3×3 box.

If exactly one extra candidate prevents that balanced BUG state, it must be
placed **provided the original puzzle has exactly one solution**. Without
this extra uniqueness assumption, the deduction is not generally valid.

```python
from sudoku.solvers.logical.solver import LogicalSolver

solver = LogicalSolver(allow_uniqueness=True)  # only for verified unique puzzles
```

The default solver keeps BUG+1 disabled. `DeductionVerifier` independently
rechecks the candidate-state conditions before the placement is executed. A
future exact-solver uniqueness check can enforce the assumption automatically.

### Simple Coloring — strong-link graph reasoning

`SimpleColoring` (`src/sudoku/solvers/logical/coloring.py`) is enabled by
**default**, and **does not assume the puzzle has a unique solution**.
For each digit, it builds a graph using *conjugate pairs*: two candidate
positions in the same row, column, or box when those are the **only two**
possible positions for that digit in the unit. It alternates two colors
along every connected component, skipping components containing contradictory
odd cycles of strong links.

It detects both conventional rules:

- **Color Wrap:** two candidates of the same color see one another; eliminate
  the digit from **every** candidate of that color in the component. The
  solver's Singles techniques can make resulting placements on the next step.
- **Color Trap:** an uncolored candidate sees at least one cell of each color
  in the same component; eliminate the digit from the uncolored cell.

Every candidate elimination is represented by a `Deduction` with the full
colored component in its `Premise.cells`. `DeductionVerifier` reconstructs
the conjugate-link component and checks that the proposed eliminations follow
from **one** rule for **one** component. It rejects forged or stale deductions.
Explanatory premise prose is not used as a proof certificate.

```python
from sudoku.solvers.logical.coloring import SimpleColoring
from sudoku.solvers.logical.solver import LogicalSolver

# Search only for coloring deductions:
solver = LogicalSolver(techniques=(SimpleColoring(),))
result = solver.solve(board, max_steps=1)

# Or use Simple Coloring with the full default technique set:
solver = LogicalSolver()
```

Test with `python -m pytest tests/solvers/logical/test_coloring.py -v`.


### Remote Pairs — alternating bivalue chains

`RemotePairs` (`src/sudoku/solvers/logical/remote_pairs.py`) is enabled by
**default**. It requires **no uniqueness assumption**. Unlike Simple Coloring,
its graph nodes are entire cells containing the *same two candidates* `{a,b}`.
Two nodes are adjacent if their cells see one another (share a row, column,
or box). Therefore their values must alternate.

For a chain of four (or any even number of) distinct bivalue cells,
consecutive nodes see each other and its two endpoints have opposite values.
Any outside cell seeing **both endpoints** cannot contain `a` or `b`. The
technique produces a structured elimination for each present pair digit.

This implementation requires at least four cells and non-peer endpoints,
leaving ordinary two-cell Naked Pairs to `NakedPair`. It skips contradictory
odd-cycle components and returns deterministic shortest witness paths.
`DeductionVerifier` independently checks the chain, candidate sets, parity,
and every proposed effect before applying it.

```python
from sudoku.solvers.logical.remote_pairs import RemotePairs
from sudoku.solvers.logical.solver import LogicalSolver

solver = LogicalSolver(techniques=(RemotePairs(),))
result = solver.solve(board, max_steps=1)
for step in result.steps:
    print(step.deduction.premises[0].description)
    print(step.deduction.eliminations)
```

Run focused tests with:
`python -m pytest tests/solvers/logical/test_remote_pairs.py -v`.


### X-Chains — alternating single-digit strong and weak links

`XChain` (`src/sudoku/solvers/logical/x_chains.py`) is enabled by
**default**, without any uniqueness assumption. It builds a graph of candidate
positions for each digit. A **strong link** connects exactly two possible
positions for the digit in one Sudoku unit, so at least one endpoint is true.
A **weak link** connects any two cells that see one another, so they cannot
both be true. Strong links also qualify as weak links when needed.

The technique searches **simple open chains** (no repeated cells) with
alternating links, starting and ending with strong links. Thus the first
and last candidate positions cannot both be false. The digit can be removed
from any *other* cell seeing both endpoints. All deductions include an
ordered chain witness in `Premise.cells`, and a readable explanation listing
the link types.

The search is intentionally bounded to avoid combinatorial explosion:
`max_links=7` (default) covers chains of 3, 5, and 7 links, i.e. **4, 6,
and 8 cells**. You can use `max_links=3`, `5`, `7`, or `9`. Longer chains,
grouped candidates, continuous/discontinuous loops, and multi-digit AICs
are not implemented by this class. Four-cell X-Chains overlap some of the
short strong-link techniques already available in the solver.

```python
from sudoku.solvers.logical.x_chains import XChain
from sudoku.solvers.logical.solver import LogicalSolver

# Use X-Chains only, with a bounded search depth:
solver = LogicalSolver(techniques=(XChain(max_links=7),))
result = solver.solve(board, max_steps=1)
for step in result.steps:
    print(step.deduction.premises[0].description)
    print(step.deduction.eliminations)
```

`DeductionVerifier` checks every strong and weak link against the *current*
candidate state, validates the length and cell uniqueness of the witness,
and checks each proposed elimination. It does not trust the English premise
as a proof certificate. Test with:

```bash
python -m pytest tests/solvers/logical/test_x_chains.py -v
```


### XY-Chains — multi-digit bivalue implication paths

`XYChain` (`src/sudoku/solvers/logical/xy_chains.py`) is enabled by **default**.
An XY-Chain consists of bivalue cells whose consecutive pairs see one another
and share a *linking candidate*. Within each cell, the alternative candidate
provides the implication to the next link.

For example, suppose we have an ordered chain of peer-linked cells with the
following candidate sets:

`{1,2} → {2,3} → {3,4} → {4,1}`.

Assume the first cell is not `1`. It must be `2`, forcing `3` in the second,
`4` in the third, and `1` in the fourth. Thus at least one endpoint contains
`1`, so candidate `1` may be removed from any **other** cell that sees both
endpoints. The exact chain geometry, candidate sets, and targets are verified
against the current `CandidateState` by `DeductionVerifier`.

The search is bounded to 4–8 cells by default, and the shorter 3-cell special
case overlaps with the already implemented XY-Wing. You can opt into 3-cell
chains or adjust the upper bound (up to 10 cells):

```python
from sudoku.solvers.logical.xy_chains import XYChain
from sudoku.solvers.logical.solver import LogicalSolver

solver = LogicalSolver(techniques=(XYChain(max_cells=8),))
result = solver.solve(board, max_steps=1)

# Include the three-bivalue-cell XY-Wing case:
technique = XYChain(min_cells=3, max_cells=6)
```

The technique makes **no uniqueness assumption**. Like the previous chain
implementations, it returns immutable `Deduction` records; it never mutates
its input candidate state. The bounded path search can be expensive on
candidate-dense puzzles, so the maximum should be raised cautiously.

```bash
python -m pytest tests/solvers/logical/test_xy_chains.py -v
```


### Almost Locked Sets (ALS-XZ)

`src/sudoku/solvers/logical/als.py` contains `AlmostLockedSet`,
`find_almost_locked_sets`, and `ALSXZ`. An **Almost Locked Set (ALS)** is a
collection of *n* empty cells in one row, column, or box whose candidate union
has exactly *n+1* digits. A single bivalue cell is the smallest ALS.

The current **ALS-XZ** technique looks for **disjoint ALSs** A and B sharing
an **RCC (Restricted Common Candidate)** `x`: every position for `x` in A sees
every position for `x` in B. Thus at most one ALS can use `x`. At least one
of the two ALSs must then become a locked set containing any other shared
candidate `z`; consequently `z` can be eliminated from every *outside* cell
that sees **all** possible `z` positions in both ALSs.

```python
from sudoku.solvers.logical.als import ALSXZ, find_almost_locked_sets
from sudoku.solvers.logical.solver import LogicalSolver

# Default max_size=3; increase to 4 for slower, broader discovery.
solver = LogicalSolver(techniques=(ALSXZ(max_size=3),))
result = solver.solve(board, max_steps=1)
```

This implementation covers the **singly-linked, non-overlapping ALS-XZ** rule.
Doubly-linked extensions, overlapping ALSs, ALS chains, and ALS-XY-Wings remain
future work. `DeductionVerifier` rechecks both candidate unions, the actual
RCC, and that every proposed elimination sees all `z` occurrences.


### ALS-Chains — linked Almost Locked Sets

`ALSChain` connects **three or more disjoint ALSs** using Restricted Common
Candidates (RCCs). Adjacent RCCs must be different. If the two endpoint ALSs
share a candidate `z` that is not the first or last RCC, at least one
endpoint must contain `z`. Therefore `z` can be eliminated from outside
cells that see **every occurrence of `z` in both endpoint ALSs**.

Each deduction records every ALS, every RCC and its candidate positions,
the terminal digit, and all proposed eliminations. Verification independently
checks that the claimed ALSs and RCCs are valid in the current candidate
state, without trusting the explanation text or rerunning graph discovery.

```python
from sudoku.solvers.logical.als_chains import ALSChain
from sudoku.solvers.logical.solver import LogicalSolver

# Use ALS-Chains alone (the default solver also includes it):
solver = LogicalSolver(techniques=(ALSChain(max_als_size=3, max_sets=4),))
result = solver.solve(board, max_steps=1)
```

The search deliberately has work limits (`max_deductions=100`,
`max_expansions=20000`) as well as ALS-size and chain-length limits. Increasing
these can find additional chains but may be computationally expensive. An
exhausted search budget should **not** be interpreted as proof that no ALS
chain exists. This first version excludes ALS overlaps, ALS loops, and
advanced multi-RCC/ALS-AIC interactions. ALS-XZ remains the efficient
specialized two-ALS implementation.

ALS-Chains use ordinary Sudoku constraints and **do not require uniqueness**.

### Sue de Coq (Two-Sector Disjoint Subsets)

`src/sudoku/solvers/logical/sue_de_coq.py` contains `SueDeCoq`.
It searches the complete unsolved intersection `C` of a line and a box
(2 or 3 cells), together with a **line-side ALS** `L` and **box-side ALS** `B`.
Writing `V` for the candidate union of the intersection, the strict pattern
requires:

- Both side groups are ALSs, containing respectively `|L|+1` and `|B|+1`
  distinct candidates.
- All side candidate digits occur in `V`, but the two side candidate sets
  are disjoint.
- The exact count is `|V| = |C| + |L| + |B|`.

These conditions confine line-side digits to `C ∪ L`, box-side digits to
`C ∪ B`, and any intersection-only digits to `C`. Elimination targets are
restricted to the appropriate line and/or box; no guessing or uniqueness
assumption is involved.

```python
from sudoku.solvers.logical.sue_de_coq import SueDeCoq

# Supports multi-cell side ALSs. Larger sizes increase search cost.
technique = SueDeCoq(max_side_size=3)
deductions = technique.find_deductions(state)
```

The default `LogicalSolver()` registers ALS-XZ, Sue de Coq, and ALS-Chains after
XY-Chains. This first version intentionally limits Sue de Coq to strict
in-intersection-candidate patterns, not broader Extended Sue de Coq.
Every deduction includes structured premises and is checked independently by
`DeductionVerifier` before its eliminations are applied.

```bash
python -m pytest tests/solvers/logical/test_als_sue_de_coq.py -v
python -m pytest tests/ -q
```

References for the mathematical rules:
[HoDoKu ALS](https://hodoku.sourceforge.net/en/tech_als.php)
and [Sue de Coq (Sudoku Clean)](https://sudokuclean.com/en/tips/sue_de_coq/).


### Generalized candidate-level Alternating Inference Chains (AICs)

`inference_graph.py` introduces an explicit candidate proposition
`CandidateNode(row, col, digit)` and a reusable `InferenceGraph` with:

- **Strong links:** at least one of two propositions must be true. For this
  implementation these come from bivalue cells and *conjugate* digit positions
  (exactly two possible cells for a digit in a row, column, or box).
- **Weak links:** two propositions cannot both be true. These come from
  different candidates in the same cell or the same candidate in a shared unit.

An AIC alternates strong and weak links. Unlike X-Chains, it may change digits
through bivalue cells; unlike XY-Chains, it may connect candidates through
strong links across houses. The engine supports:

1. **Open AICs:** `strong – weak – ... – strong`; at least one endpoint is
   true. Any *other* candidate weakly linked to both endpoints can be removed
   (including endpoints of different digits). A weak/weak discontinuity is a
   special case of this rule.
2. **Discontinuous strong/strong loops:** a false starting candidate is forced
   back to true, so it must be placed.
3. **Continuous loops:** off-loop candidates weakly linked to both ends of
   any weak edge can be eliminated.

These are standard Sudoku deductions; no uniqueness assumption is required.
Each deduction stores the ordered candidate nodes as a machine-verifiable
witness. `DeductionVerifier` **independently rebuilds** the inference graph
from the current state and validates the entire path and every effect, without
trusting free-form explanation text.

```python
from sudoku.solvers.logical.aic import AIC
from sudoku.solvers.logical.solver import LogicalSolver

# Use AIC independently; included after ALS-Chains in the default solver.
solver = LogicalSolver(techniques=(
    AIC(max_links=7, max_expansions=30000, max_deductions=60),
))
result = solver.solve(board, max_steps=1)
for step in result.steps:
    print(step.deduction.premises[0].description)
    print(step.deduction.eliminations, step.deduction.placements)
```

The search is deliberately **bounded**: open paths of up to `max_links`
(`3`, `5`, `7`, or `9`), and continuous cycles with one additional closing
weak link. Raising the expansion budget may expose longer or less accessible
chains, but stopping early does not imply no AIC exists. Grouped candidate
nodes are supported separately by `GroupedAIC` below. ALS propositions
are supported by the `ALSAIC` technique described later.

```bash
python -m pytest tests/solvers/logical/test_aic.py -v
python -m pytest tests/ -q
```

For inference rules, see
[HoDoKu Chains](https://hodoku.sourceforge.net/en/tech_chains.php) and
[SudokuWiki AIC](https://www.sudokuwiki.org/Alternating_Inference_Chains).


### Grouped Alternating Inference Chains (Grouped AICs)

The **Grouped AIC** implementation extends candidate-level AIC reasoning to
*disjunctive nodes*. `GroupNode(cells, digit)` means that **at least one** of
its two or three member cells contains the digit. Supported groups are
confined to a single intersection of a box with a row or a column; groups
are formed from **all** currently available candidate positions in that
intersection, not arbitrary hand-selected subsets.

This is important because a group is not a single cell: it may be true even
if only one of its members contains the digit. The inference graph enforces:

- **Strong link** `A = B`: at least one proposition must be true. A link
  may come from bivalue cells, conjugate pairs, or two disjoint grouped and/or
  singleton propositions covering every remaining position of a digit in a
  row, column, or box.
- **Weak link** `A - B`: the two propositions cannot both be true. When a group
  is involved, **every** possible candidate position in one proposition must
  conflict with **every** possible candidate position in the other.

For example, assume row 1 permits digit `5` only in `R1C1`, `R1C2`, and
`R1C5`. The group `(R1C1|R1C2)=5` is strongly linked to `R1C5=5`.
If a further candidate `R2C3=5` sees both members of the group (same box),
the group is weakly linked to it. If row 2 has only `R2C3` and `R2C5` as
possible positions for `5`, then the chain

```text
R1C5=5  =  (R1C1|R1C2)=5  -  R2C3=5  =  R2C5=5
```

proves that at least one endpoint contains `5`. This eliminates `5` from
other cells seeing both endpoints (for example `R3C5`).

`GroupedAIC` supports the same three types of deductions as candidate AICs:
open-chain eliminations, continuous-loop eliminations, and strong/strong
**singleton** placements. A forced grouped proposition alone does **not**
justify placing its digit in a specific cell.

```python
from sudoku.solvers.logical.grouped_aic import GroupedAIC
from sudoku.solvers.logical.solver import LogicalSolver

solver = LogicalSolver(techniques=(
    GroupedAIC(max_links=7, max_expansions=30000, max_deductions=60),
))
result = solver.solve(board, max_steps=1)
for step in result.steps:
    print(step.deduction.premises[0].description)
    print(step.deduction.eliminations, step.deduction.placements)
```

The default solver runs `GroupedAIC()` **after** the ordinary `AIC()` technique.
The search is bounded; exhausting `max_expansions` does not establish that
no valid grouped chain exists. Unlike uniqueness techniques, Grouped AIC
requires only ordinary Sudoku constraints. ALS nodes are handled by a
separate `ALSAIC` technique; a single unified grouped/ALS search is future work.

`DeductionVerifier` rebuilds the grouped inference graph for every proposed
step, checks candidate/group membership, strong and weak links, candidate
positions, chain topology, and all eliminations or placements, without relying
on free-form premise descriptions.

```bash
python -m pytest tests/solvers/logical/test_grouped_aic.py -v
python -m pytest tests/ -q
```

See [HoDoKu: Grouped Nice Loops / AICs](https://hodoku.dev/tech_chains) and
[SudokuWiki: AIC with Groups](https://www.sudokuwiki.org/AIC_with_Groups).


### Almost Locked Set Alternating Inference Chains (ALS-AICs)

`ALSAIC` extends Boolean candidate inference with **ALS-digit propositions**.
An `ALSNode(cells, d)` says that digit `d` occupies **at least one cell** of
its `cells` tuple. The cells must form an Almost Locked Set: `n` cells in a
single Sudoku unit having exactly `n+1` candidate digits.

The graph uses two fundamentally different kinds of links:

- **ALS-internal strong link:** If digits `a` and `b` belong to one ALS,
  *at least one* must occur there. Otherwise, `n` cells would have at most
  `n-1` available digits. **Do not treat this strong link as a weak link**:
  both digits might occur in the same ALS.
- **Weak link:** If every atomic assignment represented by proposition A
  conflicts with every assignment represented by proposition B, A and B
  cannot both be true. Between disjoint ALSs for the same digit, this is
  the restricted common candidate (RCC) rule.

A chain can mix ordinary candidate propositions with ALS propositions. For
example, two ALSs with a common restricted digit `3` can form the chain:

```text
ALS-A contains 2  =  ALS-A contains 3
                  -  ALS-B contains 3
                  =  ALS-B contains 2
```

The two endpoint propositions cannot both be false. Therefore, candidate
`2` can be eliminated from any *outside* cell that conflicts with all
possible `2` positions in both endpoint ALSs.

The solver handles open endpoint eliminations, continuous loops, and
strong/strong discontinuities. A forced **candidate** may yield a placement;
a forced **ALS proposition** does not identify which cell should be filled.

```python
from sudoku.solvers.logical.als_aic import ALSAIC
from sudoku.solvers.logical.solver import LogicalSolver

# Deeper ALS-AIC search, explicitly opted into for this run.
solver = LogicalSolver(techniques=(
    ALSAIC(max_links=5, max_als_size=3,
           max_als_groups=100, max_expansions=12000,
           max_deductions=40),
))
result = solver.solve(board, max_steps=1)
for step in result.steps:
    print(step.deduction.premises[0].description)
    print(step.deduction.eliminations, step.deduction.placements)
```

**Performance and scope.** By default the main `LogicalSolver` registers a
*lighter* `ALSAIC` configuration with three-link discovery, at most 35 ALSs,
and 700 graph expansions. The standalone technique supports longer chains,
ALSs of up to four cells, and adjustable search budgets. The caps make
search incomplete; finding no deduction does not prove none exists.

`DeductionVerifier` independently rebuilds the graph, checks live ALS
membership and candidates, reconstructs every strong/weak link from Sudoku
constraints, and checks all effects. Uniqueness of the puzzle is **not**
assumed. Currently ALS-AIC nodes can be mixed with **individual candidate**
nodes; box-line grouped nodes and ALS nodes in the *same* chain remain future
work. One-cell ALSs are already represented as bivalue candidate links.

```bash
python -m pytest tests/solvers/logical/test_als_aic.py -v
python -m pytest tests/ -q
```

Background: [SudokuWiki: AIC with ALSs](https://www.sudokuwiki.org/AIC_with_ALSs)
and [Sudopedia: Alternating Inference Chain](https://sudopedia.sudocue.net/index.php?title=Alternating_Inference_Chain).
