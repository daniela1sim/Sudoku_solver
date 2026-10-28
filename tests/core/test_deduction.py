"""Tests for immutable Sudoku deduction records."""

from dataclasses import FrozenInstanceError

import pytest

from sudoku.core.deduction import Deduction, Elimination, Placement, Premise, cell_label


def test_naked_single_record() -> None:
    premise = Premise("Only 4 remains", cells=((0, 2),), digits=frozenset({4}))
    deduction = Deduction("Naked Single", (premise,), placements=(Placement((0, 2), 4),))
    assert deduction.affected_cells == frozenset({(0, 2)})
    assert cell_label((0, 2)) == "R1C3"
    assert deduction.eliminations == ()


def test_pair_elimination_record() -> None:
    premises = (Premise("Two cells form the pair", ((3, 1), (3, 4)), frozenset({3, 7})),)
    deduction = Deduction("Naked Pair", premises, eliminations=(Elimination((3, 5), 3),))
    assert deduction.affected_cells == frozenset({(3, 5)})


def test_invalid_digits_rejected() -> None:
    with pytest.raises(ValueError):
        Placement((0, 0), 0)
    with pytest.raises(ValueError):
        Elimination((0, 0), 10)


def test_invalid_cells_rejected() -> None:
    with pytest.raises(IndexError):
        Placement((9, 0), 3)
    with pytest.raises(TypeError):
        Elimination([0, 0], 3)


def test_record_is_immutable() -> None:
    move = Placement((0, 2), 4)
    with pytest.raises(FrozenInstanceError):
        move.digit = 5


def test_deduction_requires_effect_and_premise() -> None:
    premise = Premise("Only 4 remains")
    with pytest.raises(ValueError):
        Deduction("Naked Single", (premise,))
    with pytest.raises(ValueError):
        Deduction("Naked Single", (), placements=(Placement((0, 2), 4),))


def test_conflicting_or_duplicate_effects_rejected() -> None:
    premise = (Premise("Reason"),)
    with pytest.raises(ValueError):
        Deduction("Example", premise, placements=(Placement((0, 2), 4), Placement((0, 2), 5)))
    with pytest.raises(ValueError):
        Deduction("Example", premise, placements=(Placement((0, 2), 4),), eliminations=(Elimination((0, 2), 3),))
    with pytest.raises(ValueError):
        Deduction("Example", premise, eliminations=(Elimination((0, 2), 3), Elimination((0, 2), 3)))
