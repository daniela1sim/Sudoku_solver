"""Targeted deduction, forgery, orientation and opt-in tests."""
import pytest
from dataclasses import replace
from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination
from sudoku.solvers.logical.rectangles import EmptyRectangle, UniqueRectangleType1
from sudoku.solvers.logical.finned_fish import FinnedXWing
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.solver import LogicalSolver


def blank():
    return CandidateState(SudokuBoard([[0]*9 for _ in range(9)]))


def state_for_er():
    s=blank()
    # Box 1: d=1 forms cross in row 1 + column 2.
    allowed={(0,0),(0,1),(1,1)}
    for r in range(3):
        for c in range(3):
            if (r,c) not in allowed:
                s._candidates[(r,c)].discard(1)
    # Conjugate row 5: R5C2 / R5C8.
    for c in range(9):
        if c not in (1,7): s._candidates[(4,c)].discard(1)
    return s


def state_for_fins(transpose=False):
    s=blank()
    def at(r,c):return (c,r) if transpose else (r,c)
    # Base row 1: col 2,5; fin row 4: col 2,5 plus fin col 6.
    for c in range(9):
        if c not in (1,4): s._candidates[at(0,c)].discard(1)
        if c not in (1,4,5): s._candidates[at(3,c)].discard(1)
    return s


def state_for_ur():
    s=blank()
    corners=((0,0),(0,3),(1,0),(1,3))
    for cell in corners[:3]: s._candidates[cell]={1,2}
    s._candidates[corners[3]]={1,2,3}
    return s


@pytest.mark.parametrize('technique,state_maker,target', [
    (EmptyRectangle,state_for_er,Elimination((0,7),1)),
    (FinnedXWing,state_for_fins,Elimination((4,4),1)),
    (UniqueRectangleType1,state_for_ur,Elimination((1,3),1)),
])
def test_finds_and_verifies(technique,state_maker,target):
    state=state_maker()
    before={cell:state.candidates_at(*cell) for cell in state.unsolved_cells()}
    deductions=technique().find_deductions(state)
    matching=[d for d in deductions if target in d.eliminations]
    assert matching, f'Expected {technique.__name__} to find {target}'
    for deduction in matching:
        DeductionVerifier.verify(state,technique(),deduction)
    assert before=={cell:state.candidates_at(*cell) for cell in state.unsolved_cells()}
    forged=replace(matching[0],eliminations=(Elimination((8,8),1),))
    with pytest.raises(ValueError):DeductionVerifier.verify(state,technique(),forged)


def test_column_finned_xwing():
    state=state_for_fins(transpose=True)
    assert any(Elimination((4,4),1) in deduction.eliminations
               for deduction in FinnedXWing().find_deductions(state))


def test_uniqueness_is_opt_in():
    assert 'Unique Rectangle Type 1' not in [t.name for t in LogicalSolver().techniques]
    assert 'Unique Rectangle Type 1' in [t.name for t in LogicalSolver(allow_uniqueness=True).techniques]
    with pytest.raises(ValueError,match='allow_uniqueness'):
        LogicalSolver((UniqueRectangleType1(),))
    LogicalSolver((UniqueRectangleType1(),),allow_uniqueness=True)
