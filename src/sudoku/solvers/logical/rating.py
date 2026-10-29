"""Versioned local difficulty estimates, inspired by the SE technique scale.

These are scores for the recorded solve path, not Sudoku Explainer ratings.
Search bounds, technique selection and ordering affect the result. Unsupported
forcing-chain families are deliberately not simulated with a guess counter.
"""

SCALE_MAX = 11.9
TECHNIQUE_SCORES = {
    "Naked Single": 2.3, "Hidden Single": 1.5,
    "Pointing": 2.6, "Claiming": 2.8,
    "Naked Pair": 3.0, "Hidden Pair": 3.4,
    "Naked Triple": 3.6, "Hidden Triple": 4.0,
    "Naked Quad": 5.0, "Hidden Quad": 5.4,
    "X-Wing": 3.2, "Swordfish": 3.8, "Jellyfish": 5.2,
    "Skyscraper": 4.0, "2-String Kite": 4.1, "Crane": 4.2,
    "XY-Wing": 4.2, "XYZ-Wing": 4.4, "W-Wing": 4.5,
    "Empty Rectangle": 4.6, "Finned X-Wing": 4.5,
    "Finned Swordfish": 5.0, "Finned Jellyfish": 5.5,
    "Simple Coloring": 6.5, "Remote Pairs": 6.6,
    "X-Chain": 6.8, "XY-Chain": 7.0,
    "ALS-XZ": 7.0, "Sue de Coq": 7.5, "ALS-Chain": 7.5,
    "AIC": 7.5, "Grouped AIC": 8.0, "ALS-AIC": 8.5,
    "Unique Rectangle Type 1": 4.5, "Unique Rectangle Type 2": 4.6,
    "Unique Rectangle Type 3": 4.7, "Unique Rectangle Type 4": 4.8,
    "Unique Rectangle Type 5": 4.9, "Unique Rectangle Type 6": 5.0,
    "Hidden Unique Rectangle": 5.0, "BUG+1": 5.6,
}


def step_score(step):
    """Recognize simpler single placements from state, not explanation text."""
    deduction = step.deduction
    if deduction.technique in ("Naked Single", "Hidden Single"):
        move = deduction.placements[0]
        r, c = move.cell
        row = [(r, col) for col in range(9)]
        column = [(rr, c) for rr in range(9)]
        box = [(rr, cc) for rr in range(r // 3 * 3, r // 3 * 3 + 3)
               for cc in range(c // 3 * 3, c // 3 * 3 + 3)]
        if any(sum(step.before.board.value_at(*cell) == 0 for cell in unit) == 1
               for unit in (row, column, box)):
            return 1.0
        for unit, score in ((box, 1.2), (row, 1.5), (column, 1.5)):
            if sum(move.digit in step.before.candidates_at(*cell) for cell in unit) == 1:
                return score
    return TECHNIQUE_SCORES.get(deduction.technique)


def estimate_rating(steps, *, complete, contradiction=False):
    """Summarize all recorded steps independently of the replay cursor.

    An incomplete path's peak is descriptive, not a difficulty lower bound:
    another solving order could avoid the technique entirely.
    """
    rated = [(step_score(step), step.deduction.technique) for step in steps]
    known = [(score, name) for score, name in rated if score is not None]
    peak, hardest = max(known, key=lambda item: item[0]) if known else (None, None)
    status = ("contradiction" if contradiction else
              "unsupported" if any(score is None for score, _ in rated) else
              "complete" if complete and steps else
              "already_complete" if complete else "incomplete")
    return {
        "method": "local-technique-v1", "scale_max": SCALE_MAX,
        "status": status,
        "score": peak if status == "complete" else None,
        "observed_peak": None if contradiction else peak,
        "hardest_technique": None if contradiction else hardest,
    }
