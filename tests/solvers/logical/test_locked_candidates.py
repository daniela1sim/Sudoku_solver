"""Regression tests for pointing, claiming, and complementary groups."""
import pytest
from sudoku.core.board import SudokuBoard
from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Elimination
from sudoku.solvers.logical.locked_candidates import Pointing, Claiming, LockedCandidates
from sudoku.solvers.logical.disjoint_groups import DisjointGroups
from sudoku.solvers.logical.verification import DeductionVerifier
from sudoku.solvers.logical.solver import LogicalSolver, SolveStatus


def blank():
    return CandidateState(SudokuBoard([[0]*9 for _ in range(9)]))


def pointing_state(axis='row'):
    s=blank()
    remaining={(0,0),(0,1)} if axis=='row' else {(0,0),(1,0)}
    for r in range(3):
        for c in range(3):
            if (r,c) not in remaining:
                s._candidates[(r,c)].discard(1)
    s._assert_consistent()
    return s


def claiming_state(axis='row'):
    s=blank()
    line=[(3,c) for c in range(9)] if axis=='row' else [(r,3) for r in range(9)]
    remaining={(3,3),(3,4)} if axis=='row' else {(3,3),(4,3)}
    for p in line:
        if p not in remaining:
            s._candidates[p].discard(2)
    s._assert_consistent()
    return s


@pytest.mark.parametrize('axis,target', [('row',(0,3)), ('column',(3,0))])
def test_pointing(axis,target):
    state=pointing_state(axis)
    before=state.copy()
    deductions=Pointing().find_deductions(state)
    match=next(d for d in deductions if Elimination(target,1) in d.eliminations)
    DeductionVerifier.verify(state,Pointing(),match)
    assert state.candidates_at(*target)==before.candidates_at(*target)
    assert LogicalSolver((Pointing(),)).solve(state,max_steps=1).steps


@pytest.mark.parametrize('axis,target', [('row',(4,3)), ('column',(3,4))])
def test_claiming(axis,target):
    state=claiming_state(axis)
    deductions=Claiming().find_deductions(state)
    match=next(d for d in deductions if Elimination(target,2) in d.eliminations)
    DeductionVerifier.verify(state,Claiming(),match)
    assert LogicalSolver((Claiming(),)).solve(state,max_steps=1).steps


def test_invalid_locked_candidate_target_rejected():
    state=pointing_state('row')
    deduction=next(d for d in Pointing().find_deductions(state)
                   if Elimination((0,3),1) in d.eliminations)
    forged=Deduction(deduction.technique, deduction.premises,
                     eliminations=(Elimination((4,4),1),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state,Pointing(),forged)


def test_invalid_mode():
    with pytest.raises(ValueError):
        LockedCandidates('other')


def test_disjoint_groups_are_complement_of_naked_subset():
    state=blank()
    state._candidates[(0,0)]={1,2}
    state._candidates[(0,1)]={1,2}
    state._assert_consistent()
    deductions=DisjointGroups().find_deductions(state)
    match=next(d for d in deductions if Elimination((0,2),1) in d.eliminations)
    DeductionVerifier.verify(state,DisjointGroups(),match)
    assert 'disjoint' in match.premises[0].description
    assert LogicalSolver((DisjointGroups(),)).solve(state,max_steps=1).status==SolveStatus.STEP_LIMIT


def test_disjoint_groups_reject_unrelated_elimination():
    state=blank()
    state._candidates[(0,0)]={1,2}
    state._candidates[(0,1)]={1,2}
    match=next(d for d in DisjointGroups().find_deductions(state)
               if Elimination((0,2),1) in d.eliminations)
    forged=Deduction(match.technique,match.premises,
                     eliminations=(Elimination((4,4),1),))
    with pytest.raises(ValueError):
        DeductionVerifier.verify(state,DisjointGroups(),forged)
