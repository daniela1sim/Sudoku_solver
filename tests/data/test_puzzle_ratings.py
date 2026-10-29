"""Check local technique ratings and repeatable JSONL enrichment semantics."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from scripts.rate_puzzles import (
    RATING_METHOD, enrich_records, is_current, rate_puzzle, rate_with_timeout,
    rating_config, read_records, write_records_atomic,
)
from sudoku.solvers.logical.rating import estimate_rating
from sudoku.solvers.logical.solver import LogicalSolver
from sudoku.core.board import SudokuBoard

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "puzzles.jsonl"


@pytest.fixture(scope="module")
def records():
    return read_records(DATA_FILE)


def test_all_puzzles_retain_original_metadata_and_valid_rating_schema(records):
    assert len(records) == 144
    for record in records:
        rating = record["rating"]
        assert rating["method"] == RATING_METHOD
        assert rating["scale_max"] == 11.9
        assert rating["config"] == rating_config()
        assert rating["status"] in {"complete", "incomplete", "step_limit", "timeout", "error", "unsupported"}
        if rating["status"] == "complete":
            assert rating["logical_status"] == "solved"
            assert rating["score"] == rating["observed_peak"]
            assert 1 <= rating["score"] <= 8.5
            assert rating["hardest_technique"] is not None
            assert isinstance(rating["technique_counts"], dict)
            assert sum(rating["technique_counts"].values()) == rating["steps"]
        else:
            assert rating["score"] is None
        assert record["difficulty"] in {"easy", "medium", "hard", "expert"}
        assert 81 - record["puzzle"].count("0") == record["givens"]
        assert all(clue == "0" or clue == digit for clue, digit in zip(record["puzzle"], record["solution"]))


@pytest.mark.parametrize("id_", ["EASY-001", "MEDIUM-001", "HARD-001", "EXPERT-001"])
def test_saved_ratings_match_full_logical_solver(records, id_):
    record = next(r for r in records if r["id"] == id_)
    expected = rate_puzzle(record["puzzle"])
    assert record["rating"] == expected
    result = LogicalSolver().solve(SudokuBoard.from_string(record["puzzle"]))
    calculated = estimate_rating(result.steps, complete=result.solved)
    assert expected["observed_peak"] == calculated["observed_peak"]
    assert expected["score"] == calculated["score"]


def test_step_limit_is_never_mistaken_for_a_final_rating(records):
    rating = rate_puzzle(records[0]["puzzle"], max_steps=2)
    assert rating["status"] == "step_limit"
    assert rating["logical_status"] == "step_limit"
    assert rating["score"] is None
    assert rating["steps"] == 2
    assert rating["config"]["max_steps"] == 2


def test_timeout_cannot_be_mistaken_for_an_unsolvable_puzzle(records):
    rating = rate_with_timeout(records[0]["puzzle"], timeout_seconds=0.0001)
    assert rating["status"] == "timeout"
    assert rating["score"] is None
    assert rating["observed_peak"] is None
    assert rating["logical_status"] is None


def test_cache_and_force_behavior_without_mutating_other_fields(tmp_path, monkeypatch, records):
    import scripts.rate_puzzles as rater
    original = {key: value for key, value in records[0].items() if key != "rating"}
    fresh = [dict(records[0])]
    def fail(*args, **kwargs):
        raise AssertionError("Should reuse the existing rating")
    monkeypatch.setattr(rater, "rate_with_timeout", fail)
    output = tmp_path / "rated.jsonl"
    counts = enrich_records(fresh, timeout_seconds=5, save_to=output)
    assert counts == Counter({"skipped": 1})
    assert not output.exists()
    assert {key: value for key, value in fresh[0].items() if key != "rating"} == original
    assert is_current(fresh[0]["rating"], max_steps=None)
    assert not is_current(fresh[0]["rating"], max_steps=5)

    monkeypatch.setattr(rater, "rate_with_timeout", lambda *a, **k: dict(fresh[0]["rating"]))
    counts = enrich_records(fresh, timeout_seconds=5, force=True, save_to=output)
    assert counts == Counter({fresh[0]["rating"]["status"]: 1})
    assert read_records(output) == fresh


def test_atomic_jsonl_round_trip_preserves_order_and_extra_keys(tmp_path, records):
    output = tmp_path / "new" / "puzzles.jsonl"
    subset = [records[3], records[0]]
    write_records_atomic(output, subset)
    assert read_records(output) == subset
    assert [r["id"] for r in read_records(output)] == [subset[0]["id"], subset[1]["id"]]
    assert all(json.loads(line).get("logical_profile") for line in output.read_text().splitlines())
