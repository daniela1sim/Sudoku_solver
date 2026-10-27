Intelligent Sudoku Solver

An extensible Python project for solving Sudoku puzzles with human-style logical deductions, mathematical constraint-solving algorithms, and eventually machine-learning-assisted strategies.

The central goal is not merely to produce a completed grid, but to make the solving process correct, traceable, and explainable: every logical placement or candidate elimination should be supported by an explicit justification.
Project status: Early development / initial architecture. The features below describe the development roadmap and are not yet implemented unless noted otherwise.

Project goals
1. Explainable logical solving: Implement human Sudoku techniques, from singles and subsets to advanced patterns and inference chains. Record the premises and consequences of each deduction.
2. Constraint solving: Implement and compare backtracking, constraint propagation, search heuristics, and exact-cover methods.
3. ML/LLM experiments: Investigate whether learned heuristics or LLM-assisted technique selection can improve existing solvers without compromising correctness.
4. Puzzle input and visualization: Eventually support structured grids, image recognition, and interactive step-by-step explanations.
Development roadmap

Phase 1 — Human-style logical solver
- [ ] Define a SudokuBoard representation and validate puzzle constraints.
- [ ] Track candidate sets for empty cells.
- [ ] Design immutable, structured Deduction records for placements, eliminations, and supporting premises.
- [ ] Implement Naked Singles and Hidden Singles.
- [ ] Implement Locked Candidates and Naked/Hidden Subsets.
- [ ] Add advanced techniques (e.g., X-Wing, Swordfish, XY-Wing, coloring, and inference chains).
- [ ] Preserve a reproducible solving history with human-readable explanations.
- [ ] Add unit and integration tests for techniques, contradictions, and invalid inputs.

Phase 2 — Mathematical constraint solvers
- [ ] Implement baseline backtracking.
- [ ] Add heuristics such as Minimum Remaining Values (MRV) and forward checking.
- [ ] Implement Algorithm X / exact cover.
- [ ] Compare results with an established solver (e.g., Z3).
- [ ] Benchmark solve time, search nodes, backtracks, and memory usage.
- [ ] Evaluate combinations of logical preprocessing and search.

Phase 3 — ML and LLM experiments
- [ ] Establish benchmark datasets and reproducible evaluation procedures.
- [ ] Test model-guided search or technique selection against conventional heuristics.
- [ ] Explore structured explanations generated from verified deductions.
- [ ] Measure correctness, computational cost, and performance gains.

Future extensions
- [ ] Read Sudoku puzzles from images using computer vision and digit recognition.
- [ ] Build an interactive application for replaying deductions and requesting hints.
- [ ] Allow users to choose which logical techniques the solver may use.

Proposed repository structure
The repository will grow incrementally. The initial package structure is planned as:
intelligent-sudoku-solver/
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── src/
│   └── sudoku/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── board.py
│       │   ├── candidates.py
│       │   ├── deduction.py
│       │   └── validator.py
│       └── solvers/
│           ├── __init__.py
│           └── logical/
│               ├── __init__.py
│               ├── base.py
│               ├── singles.py
│               └── solver.py
├── tests/
│   ├── core/
│   └── solvers/
│       └── logical/
└── data/
    └── puzzles/

Future modules may include solvers/constraint/, solvers/hybrid/, ml/, vision/, explanation/, visualization/, and benchmarks/.

Design principles
- Correctness first: Never apply an unsupported elimination or placement. Validate the final grid independently.
- Separate discovery from mutation: Techniques propose deductions; a central solver checks and applies them.
- Structured reasoning: A deduction stores the technique, relevant cells/candidates, premises, and effects independently of its textual explanation.
- Shared core: Logical, mathematical, and learned solvers use compatible puzzle representations.
- Testability: Each technique and algorithm has focused tests and regression cases.
- Reproducibility: Compare approaches on the same puzzles and report clearly defined metrics.

Representation conventions
- Classic 9 × 9 Sudoku, with digits 1 through 9.
- Empty cells are represented by 0.
- Internal cell coordinates are zero-based (row, column) pairs.
- Explanations use familiar one-based notation (for example, R4C6).
- Candidate eliminations must persist in the logical solver's state; they should not be lost by recomputing candidates solely from placed digits.
Example puzzle format
A puzzle can be represented as a list of nine rows:
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
The public Python API and CLI will be documented once implemented.
Testing and benchmarks
Planned tests cover valid placements, candidate updates, each logical technique, invalid puzzles, unsatisfiable puzzles, and puzzles with multiple solutions. Benchmarks will distinguish human-style difficulty from algorithmic search complexity, which need not correlate.
Contributing
The project is in its initial design stage. Contribution guidelines will be added as the implementation matures.
License
A license will be selected and included in LICENSE before public distribution.
