"""App technique catalog derived from the solver's registered defaults."""

from sudoku.solvers.logical.solver import LogicalSolver


def catalog():
    ordinary = {t.name for t in LogicalSolver().techniques}
    return [
        {"name": t.name, "requires_uniqueness": t.name not in ordinary}
        for t in LogicalSolver(allow_uniqueness=True).techniques
    ]


def selected_solver(names=None, *, allow_uniqueness=False):
    available = LogicalSolver(allow_uniqueness=allow_uniqueness)
    if names is None:
        return available
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError("Techniques must be a list of technique names")
    if len(names) != len(set(names)):
        raise ValueError("Technique names must not repeat")
    allowed = {t.name for t in available.techniques}
    if set(names) - allowed:
        raise ValueError("Unknown or disabled techniques: " + ', '.join(sorted(set(names) - allowed)))
    # Selection never changes the established easiest-first solver order.
    return LogicalSolver((t for t in available.techniques if t.name in names),
                         allow_uniqueness=allow_uniqueness)
