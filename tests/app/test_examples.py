from pathlib import Path
import re

import pytest

from sudoku.core.board import SudokuBoard
from sudoku.solvers.logical.singles import NakedSingle, HiddenSingle
from sudoku.solvers.logical.solver import LogicalSolver


@pytest.mark.parametrize('name,required', [
    ('Advanced · Skyscrapers', 'Skyscraper'),
    ('Advanced · Empty rectangles', 'Empty Rectangle'),
])
def test_advanced_examples_solve_and_use_the_advertised_technique(name, required):
    source = Path('src/sudoku/app/static/app.js').read_text(encoding='utf-8')
    puzzle = re.search(r"name: '" + re.escape(name) + r"'.*?puzzle: '([0-9]{81})'", source, re.S).group(1)
    board = SudokuBoard.from_string(puzzle)
    assert not LogicalSolver((NakedSingle(), HiddenSingle())).solve(board).solved
    result = LogicalSolver().solve(board)
    assert result.solved
    assert required in {step.deduction.technique for step in result.steps}
