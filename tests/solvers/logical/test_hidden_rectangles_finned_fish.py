"""Regression tests for Hidden UR and generalized standard finned fish."""
from dataclasses import replace
import pytest
from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Elimination
from sudoku.solvers.logical.rectangles import HiddenUniqueRectangle
from sudoku.solvers.logical.finned_fish import FinnedSwordfish, FinnedJellyfish
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.solver import LogicalSolver


def fresh():
    return CandidateState(SudokuBoard([[0] * 9 for _ in range(9)]))


def hidden_state():
    state = fresh()
    corners = ((0, 0), (0, 3), (1, 0), (1, 3))
    state._candidates[(0,0)] = {1,2}
    for c in corners[1:]:
        state._candidates[c] = {1,2,3}
    # 1 is restricted to the two corners in target's row and column.
    for c in range(9):
        if c not in (0,3):
            state._candidates[(1,c)].discard(1)
    for r in range(9):
        if r not in (0,1):
            state._candidates[(r,3)].discard(1)
    return state


def fish_state(size, transpose=False):
    state = fresh()
    bases = (0,3,6) if size == 3 else (0,2,3,6)
    covers = (0,3,6) if size == 3 else (0,2,3,6)
    positions = ({0:{0,3},3:{0,3,4,6},6:{3,6}} if size == 3 else
                 {0:{0,2},2:{2,3},3:{0,3,4,6},6:{3,6}})
    def cell(r,c): return (c,r) if transpose else (r,c)
    for r in range(9):
        for c in range(9):
            state._candidates[cell(r,c)].discard(1)
    for r, cols in positions.items():
        for c in cols: state._candidates[cell(r,c)].add(1)
    target = cell(4,3)
    state._candidates[target].add(1)
    return state, target


def test_hidden_rectangle_is_opt_in_and_verified():
    state = hidden_state()
    tech = HiddenUniqueRectangle()
    found = [d for d in tech.find_deductions(state)
             if Elimination((1,3), 2) in d.eliminations]
    assert found
    DeductionVerifier.verify(state, tech, found[0])
    assert tech.name not in [t.name for t in LogicalSolver().techniques]
    assert tech.name in [t.name for t in LogicalSolver(allow_uniqueness=True).techniques]
    with pytest.raises(ValueError):
        LogicalSolver(techniques=(tech,))
    forged = replace(found[0], eliminations=(Elimination((8,8), 9),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state, tech, forged)


def test_hidden_rectangle_requires_two_extra_corners():
    state = hidden_state()
    state._candidates[(0,3)] = {1,2}
    state._candidates[(1,0)] = {1,2}
    assert HiddenUniqueRectangle().find_deductions(state) == ()


@pytest.mark.parametrize('cls,size', [(FinnedSwordfish,3),(FinnedJellyfish,4)])
@pytest.mark.parametrize('transpose', [False, True])
def test_finned_fish_both_orientations(cls,size,transpose):
    state, target = fish_state(size,transpose)
    tech = cls()
    found = [d for d in tech.find_deductions(state) if Elimination(target,1) in d.eliminations]
    assert found
    DeductionVerifier.verify(state,tech,found[0])
    forged = replace(found[0], eliminations=(Elimination((8,8),9),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state,tech,forged)


def test_finned_fish_does_not_eliminate_when_fins_separated():
    state,target = fish_state(3)
    state._candidates[(3,4)].discard(1)
    state._candidates[(3,8)].add(1)
    assert all(Elimination(target,1) not in d.eliminations
               for d in FinnedSwordfish().find_deductions(state))


def test_finned_fish_nonmutating():
    state,_ = fish_state(3)
    snapshot = {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
    FinnedSwordfish().find_deductions(state)
    assert snapshot == {cell: state.candidates_at(*cell) for cell in state.unsolved_cells()}
