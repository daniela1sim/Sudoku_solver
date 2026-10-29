"""Validate the generated, versioned dataset and independent solver agreement."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.solvers.constraint import ExactCoverSolver, PropagationSolver, ReferenceSolver
from sudoku.solvers.hybrid import HybridSolver, HybridStatus
from sudoku.solvers.logical.singles import NakedSingle, HiddenSingle
from sudoku.solvers.logical.solver import LogicalSolver

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "puzzles.jsonl"
TIERS = ("easy", "medium", "hard", "expert")


def read_records() -> list[dict]:
    return [json.loads(line) for line in DATA_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def records() -> list[dict]:
    return read_records()


def test_dataset_is_balanced_unique_and_well_formed(records):
    assert len(records) == 144
    assert Counter(r["difficulty"] for r in records) == {tier: 36 for tier in TIERS}
    assert len({r["id"] for r in records}) == len(records)
    assert len({r["puzzle"] for r in records}) == len(records)
    assert len({r["solution"] for r in records}) == len(records)
    for r in records:
        assert len(r["puzzle"]) == len(r["solution"]) == 81
        assert set(r["puzzle"]) <= set("0123456789")
        assert set(r["solution"]) <= set("123456789")
        assert SudokuBoard.from_string(r["solution"]).is_complete()
        assert SudokuBoard.from_string(r["puzzle"]).is_valid()
        assert all(clue == "0" or clue == digit for clue, digit in zip(r["puzzle"], r["solution"]))
        assert r["givens"] == 81 - r["puzzle"].count("0")
        assert r["reference_nodes"] > 0
        assert r["reference_branches"] >= 0
        statuses = r["logical_profile"]
        if r["difficulty"] == "easy":
            assert statuses["singles"]["status"] == "solved"
        elif r["difficulty"] == "medium":
            assert statuses["singles"]["status"] == "stuck"
            assert statuses["basic"]["status"] == "solved"
        elif r["difficulty"] == "hard":
            assert statuses["singles"]["status"] == "stuck"
            assert statuses["basic"]["status"] == "stuck"
            assert statuses["advanced"]["status"] == "solved"
        else:
            assert all(status["status"] == "stuck" for status in statuses.values())


@pytest.mark.parametrize("backend", [ReferenceSolver, PropagationSolver, ExactCoverSolver])
def test_all_puzzles_have_exactly_one_expected_completion(records, backend):
    solver = backend()
    for record in records:
        result = solver.analyze(record["puzzle"], limit=2)
        assert result.is_unique and result.exhaustive, (backend.__name__, record["id"])
        assert result.solutions == (record["solution"],), (backend.__name__, record["id"])


def test_hybrid_preserves_solution_across_tiers(records):
    singles = LogicalSolver(techniques=[NakedSingle(), HiddenSingle()])
    hybrid = HybridSolver(mode="hybrid", constraint_algorithm="exact_cover", logical_solver=singles)
    for tier in TIERS:
        for record in [r for r in records if r["difficulty"] == tier][:3]:
            result = hybrid.solve(record["puzzle"], solution_limit=2)
            assert result.status is HybridStatus.SOLVED
            assert result.first_solution.to_string() == record["solution"]
            if tier != "easy":
                assert result.used_fallback
                assert result.constraint_result.is_unique


def test_small_generation_is_reproducible():
    # Import the standalone generator without requiring scripts to be a package.
    import importlib.util
    module_path = DATA_FILE.parent.parent / "scripts" / "generate_puzzles.py"
    spec = importlib.util.spec_from_file_location("sudoku_generate_puzzles", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    first, a = module.generate(count_per_tier=1, seed=4242, max_attempts=1000)
    second, b = module.generate(count_per_tier=1, seed=4242, max_attempts=1000)
    assert a == b and first == second
    assert {r["difficulty"] for r in first} == set(TIERS)


def test_difficulty_labels_replay_with_current_techniques(records):
    """Fail explicitly if a change to the logical solver invalidates saved labels."""
    import importlib.util
    module_path = DATA_FILE.parent.parent / "scripts" / "generate_puzzles.py"
    spec = importlib.util.spec_from_file_location("sudoku_generate_puzzles", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    evaluators = module.difficulty_evaluators()
    for record in records:
        tier, profile = module.classify(record["puzzle"], evaluators)
        assert tier == record["difficulty"], record["id"]
        assert profile == record["logical_profile"], record["id"]


def test_optional_milp_agrees_on_all_difficulty_groups(records):
    pytest.importorskip("scipy")
    from sudoku.solvers.constraint import IntegerProgrammingSolver

    solver = IntegerProgrammingSolver()
    for tier in TIERS:
        for record in [r for r in records if r["difficulty"] == tier][:5]:
            result = solver.analyze(record["puzzle"], limit=2)
            assert result.is_unique and result.solutions == (record["solution"],)
