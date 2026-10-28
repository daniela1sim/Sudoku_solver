"""Technique-specific validation of proposed Sudoku deductions.

Verification checks that the proposed effects follow from the *current*
CandidateState. Premise descriptions are explanatory annotations and are not
yet machine-checked proof certificates.

Supported techniques include singles, subsets, fish, wings, and rectangles.
"""

from __future__ import annotations

from sudoku.core.candidates import CandidateState
from sudoku.core.deduction import Deduction, Placement, Elimination
from sudoku.solvers.logical.base import LogicalTechnique
from sudoku.solvers.logical.locked_candidates import LockedCandidates, Pointing, Claiming, _locked_patterns
from sudoku.solvers.logical.disjoint_groups import DisjointGroups
from sudoku.solvers.logical.fish import BasicFish, XWing, Swordfish, Jellyfish
from sudoku.solvers.logical.strong_links import Skyscraper, TwoStringKite, Crane, _strong_link_patterns
from sudoku.solvers.logical.wings import XYWing, XYZWing, WWing, _wing_patterns
from sudoku.solvers.logical.rectangles import EmptyRectangle, UniqueRectangleType1, UniqueRectangleType2, UniqueRectangleType3, UniqueRectangleType4, UniqueRectangleType5, UniqueRectangleType6, HiddenUniqueRectangle, _hidden_rectangle_patterns, _empty_rectangle_patterns, _UNIQUE_RECTANGLE_PATTERNS
from sudoku.solvers.logical.finned_fish import FinnedXWing, FinnedSwordfish, FinnedJellyfish
from sudoku.solvers.logical.fish_proofs import (
    verify_basic_fish, verify_finned_xwing, verify_general_finned_fish,
)
from sudoku.solvers.logical.uniqueness import BUGPlusOne, _bug_plus_one_patterns
from sudoku.solvers.logical.remote_pairs import RemotePairs, _pair_components
from sudoku.solvers.logical.x_chains import XChain, _chain_graph, _chain_eliminations
from sudoku.solvers.logical.xy_chains import XYChain, _xy_chain_eliminations
from sudoku.solvers.logical.als import ALSXZ, is_als, _candidate_union
from sudoku.solvers.logical.als_chains import ALSChain
from sudoku.solvers.logical.aic import AIC
from sudoku.solvers.logical.grouped_aic import GroupedAIC
from sudoku.solvers.logical.als_aic import ALSAIC, _eliminations as _als_aic_eliminations
from sudoku.solvers.logical.als_inference_graph import ALSNode, ALSInferenceGraph, members as als_members
from sudoku.solvers.logical.grouped_inference_graph import GroupNode, GroupedInferenceGraph, members
from sudoku.solvers.logical.inference_graph import CandidateNode, InferenceGraph
from sudoku.solvers.logical.sue_de_coq import SueDeCoq
from sudoku.solvers.logical.strong_links import _sees
from sudoku.solvers.logical.coloring import (
    SimpleColoring, _colored_components, _wrap_effects, _trap_effects,
)
from sudoku.solvers.logical.singles import HiddenSingle, NakedSingle, _units
from sudoku.solvers.logical.subsets import (
    HiddenSubset, NakedSubset, HiddenPair, NakedPair,
    HiddenTriple, NakedTriple, HiddenQuad, NakedQuad,
)


class DeductionVerifier:
    """Check deductions without mutating the solving state."""

    _SUPPORTED = (NakedSingle, HiddenSingle, NakedSubset, HiddenSubset,
                  NakedPair, HiddenPair, NakedTriple, HiddenTriple, NakedQuad, HiddenQuad,
                  LockedCandidates, Pointing, Claiming, DisjointGroups,
                  BasicFish, XWing, Swordfish, Jellyfish,
                  Skyscraper, TwoStringKite, Crane, XYWing, XYZWing, WWing,
                  EmptyRectangle, UniqueRectangleType1, UniqueRectangleType2, UniqueRectangleType3, UniqueRectangleType4, UniqueRectangleType5, UniqueRectangleType6, HiddenUniqueRectangle, FinnedXWing, FinnedSwordfish, FinnedJellyfish, BUGPlusOne, SimpleColoring, RemotePairs, XChain, XYChain, ALSXZ, ALSChain, SueDeCoq, AIC, GroupedAIC, ALSAIC)

    @classmethod
    def supports(cls, technique: LogicalTechnique) -> bool:
        """Whether this exact technique implementation has a verifier."""
        return type(technique) in cls._SUPPORTED

    @classmethod
    def verify(
        cls, state: CandidateState, technique: LogicalTechnique, deduction: Deduction
    ) -> None:
        """Raise ValueError for an invalid deduction, or NotImplementedError if unsupported.

        Success is indicated by returning None. This method does not mutate state.
        """
        if not cls.supports(technique):
            raise NotImplementedError(f"No verifier for {type(technique).__name__}")
        if isinstance(technique, ALSAIC):
            cls._verify_als_aic(state, technique, deduction)
            return
        if isinstance(technique, GroupedAIC):
            cls._verify_grouped_aic(state, technique, deduction)
            return
        if isinstance(technique, AIC):
            cls._verify_aic(state, technique, deduction)
            return
        if isinstance(technique, ALSChain):
            cls._verify_als_chain(state, technique, deduction)
            return
        if isinstance(technique, ALSXZ):
            cls._verify_als_xz(state, technique, deduction)
            return
        if isinstance(technique, SueDeCoq):
            cls._verify_sue_de_coq(state, technique, deduction)
            return
        if isinstance(technique, XYChain):
            cls._verify_xy_chain(state, technique, deduction)
            return
        if isinstance(technique, XChain):
            cls._verify_x_chain(state, technique, deduction)
            return
        if isinstance(technique, RemotePairs):
            cls._verify_remote_pairs(state, technique, deduction)
            return
        if isinstance(technique, SimpleColoring):
            cls._verify_simple_coloring(state, technique, deduction)
            return
        if isinstance(technique, BUGPlusOne):
            cls._verify_bug_plus_one(state, technique, deduction)
            return
        if isinstance(technique, (FinnedXWing, FinnedSwordfish, FinnedJellyfish)):
            cls._verify_finned_fish(state, technique, deduction)
            return
        if isinstance(technique, (EmptyRectangle, UniqueRectangleType1, UniqueRectangleType2, UniqueRectangleType3, UniqueRectangleType4, UniqueRectangleType5, UniqueRectangleType6, HiddenUniqueRectangle)):
            cls._verify_new_patterns(state, technique, deduction)
            return
        if isinstance(technique, (XYWing, XYZWing, WWing)):
            cls._verify_wings(state, technique, deduction)
            return
        if isinstance(technique, (Skyscraper, TwoStringKite, Crane)):
            cls._verify_strong_links(state, technique, deduction)
            return
        if isinstance(technique, BasicFish):
            cls._verify_fish(state, technique, deduction)
            return
        if isinstance(technique, (LockedCandidates, DisjointGroups)):
            cls._verify_pattern(state, technique, deduction)
            return
        if isinstance(technique, (NakedSubset, HiddenSubset)):
            cls._verify_subset(state, technique, deduction)
            return
        if (
            deduction.technique != technique.name
            or len(deduction.placements) != 1
            or deduction.eliminations
        ):
            raise ValueError("Unexpected deduction shape or technique name")

        placement = deduction.placements[0]
        row, col = placement.cell
        digit = placement.digit
        if digit not in state.candidates_at(row, col):
            raise ValueError("Placement digit is not an available candidate")

        if type(technique) is NakedSingle:
            if state.candidates_at(row, col) != frozenset({digit}):
                raise ValueError("Invalid Naked Single")
        elif type(technique) is HiddenSingle:
            row_cells = ((row, c) for c in range(9))
            col_cells = ((r, col) for r in range(9))
            box_row = (row // 3) * 3
            box_col = (col // 3) * 3
            box_cells = (
                (r, c)
                for r in range(box_row, box_row + 3)
                for c in range(box_col, box_col + 3)
            )
            if not any(
                sum(digit in state.candidates_at(*cell) for cell in unit) == 1
                for unit in (row_cells, col_cells, box_cells)
            ):
                raise ValueError("Invalid Hidden Single")



    @staticmethod
    def _verify_als_aic(
        state: CandidateState, technique: ALSAIC, deduction: Deduction
    ) -> None:
        """Validate every ALS proposition, link, and proposed effect afresh.

        Candidate membership is checked against a reconstructed inference
        graph. Strong ALS-internal edges are NOT treated as weak edges.
        The free-text explanation never establishes truth of a link.
        """
        if deduction.technique != technique.name or len(deduction.premises) < 4:
            raise ValueError("Invalid ALS-AIC deduction header or witness length")
        graph = ALSInferenceGraph(state, max_als_size=technique.max_als_size,
                                  max_als_groups=technique.max_als_groups)
        path = []
        for premise in deduction.premises:
            if len(premise.digits) != 1:
                raise ValueError("Each ALS-AIC proposition needs one digit")
            digit = next(iter(premise.digits))
            if len(premise.cells) == 1:
                node = CandidateNode(*premise.cells[0], digit)
            elif 2 <= len(premise.cells) <= technique.max_als_size:
                node = ALSNode(premise.cells, digit)
            else:
                raise ValueError("Invalid ALS-AIC node size")
            if node not in graph.strong:
                raise ValueError("ALS-AIC witness refers to a nonexistent proposition")
            path.append(node)
        if not any(isinstance(n, ALSNode) for n in path):
            raise ValueError("An ALS-AIC must include an ALS node")
        closed = path[0] == path[-1]
        if len(path) - 1 > technique.max_links + (1 if closed else 0):
            raise ValueError("ALS-AIC exceeds the configured link bound")
        if closed:
            if len(path) < 4 or len(set(path[:-1])) != len(path) - 1:
                raise ValueError("ALS-AIC closed path has repeated nodes")
        elif len(set(path)) != len(path):
            raise ValueError("ALS-AIC open path has repeated nodes")
        for i, (a, b) in enumerate(zip(path, path[1:])):
            kind = "strong" if i % 2 == 0 else "weak"
            if not graph.linked(a, b, kind):
                raise ValueError(f"Invalid ALS-AIC {kind} link at index {i}")
        if closed and (len(path) - 1) % 2 == 1:
            # Strong/strong discontinuity: only a candidate singleton can
            # be directly placed. A forced ALS-level OR is not a placement.
            start = path[0]
            if not isinstance(start, CandidateNode) or deduction.eliminations or (
                deduction.placements != (Placement(start.cell, start.digit),)
            ):
                raise ValueError("Invalid ALS-AIC strong/strong placement")
            return
        if deduction.placements or not deduction.eliminations:
            raise ValueError("ALS-AIC must contain valid eliminations only")
        if closed and (len(path) - 1) % 2 != 0:
            raise ValueError("Continuous ALS-AIC loop requires even links")
        if not closed and ((len(path) - 1) < 3 or (len(path) - 1) % 2 == 0):
            raise ValueError("Open ALS-AIC must have an odd number of links >= 3")
        allowed = set(_als_aic_eliminations(graph, state, tuple(path), closed=closed))
        if not set(deduction.eliminations).issubset(allowed):
            raise ValueError("Unjustified ALS-AIC elimination")

    @staticmethod
    def _verify_grouped_aic(
        state: CandidateState, technique: GroupedAIC, deduction: Deduction
    ) -> None:
        """Rebuild and verify every grouped proposition, link, and effect.

        Unlike the discoverer, this method does not search for chains. It
        interprets the recorded path against a freshly constructed graph.
        Free-form descriptions have no role in the mathematical proof.
        """
        if deduction.technique != technique.name or len(deduction.premises) < 4:
            raise ValueError("Invalid Grouped AIC technique or witness length")
        graph = GroupedInferenceGraph(state)
        path = []
        for premise in deduction.premises:
            if len(premise.digits) != 1 or not 1 <= len(premise.cells) <= 3:
                raise ValueError("A grouped node must contain one digit and 1–3 cells")
            digit = next(iter(premise.digits))
            if len(premise.cells) == 1:
                node = CandidateNode(*premise.cells[0], digit)
            else:
                if premise.cells != tuple(sorted(premise.cells)):
                    raise ValueError("Grouped AIC cells must be sorted")
                node = GroupNode(premise.cells, digit)
            if node not in graph.strong:
                raise ValueError("Grouped AIC refers to a nonexistent candidate group")
            path.append(node)
        if not any(isinstance(node, GroupNode) for node in path):
            raise ValueError("Grouped AIC requires at least one grouped node")
        closed = path[0] == path[-1]
        unique_nodes = path[:-1] if closed else path
        if len(set(unique_nodes)) != len(unique_nodes):
            raise ValueError("Grouped AIC repeats a node")
        atoms = [atom for node in unique_nodes for atom in members(node)]
        if len(set(atoms)) != len(atoms):
            raise ValueError("Grouped AIC overlaps atomic candidate positions")
        count = len(path) - 1
        if count < 3 or count > technique.max_links + int(closed and count % 2 == 0):
            raise ValueError("Grouped AIC chain exceeds configured length")
        for index, (a, b) in enumerate(zip(path, path[1:])):
            kind = "strong" if index % 2 == 0 else "weak"
            if not graph.linked(a, b, kind):
                raise ValueError(f"Invalid Grouped AIC {kind} link at {index}")
        if deduction.placements:
            if (not closed or count % 2 != 1 or isinstance(path[0], GroupNode)
                    or deduction.eliminations
                    or deduction.placements != (Placement(path[0].cell, path[0].digit),)):
                raise ValueError("Invalid grouped strong/strong loop placement")
            return
        if not deduction.eliminations:
            raise ValueError("Grouped AIC must propose a placement or elimination")
        if closed:
            if count % 2 != 0 or count < 4:
                raise ValueError("Grouped AIC continuous loop must close weakly")
        elif count % 2 != 1:
            raise ValueError("Open Grouped AIC must start and end strongly")
        # Derive allowed effects from the reconstructed graph, independently
        # from the discoverer's effect-generation helper.
        on_chain = set(atoms)
        if closed:
            allowed_nodes = set()
            for index, (a, b) in enumerate(zip(path, path[1:])):
                if index % 2 == 1:
                    allowed_nodes.update(graph.common_candidate_conflicts(a, b))
        else:
            allowed_nodes = set(graph.common_candidate_conflicts(path[0], path[-1]))
        permitted = {Elimination(n.cell, n.digit) for n in allowed_nodes - on_chain}
        if any(effect not in permitted for effect in deduction.eliminations):
            raise ValueError("Grouped AIC elimination is not justified by the witness")

    @staticmethod
    def _verify_aic(
        state: CandidateState, technique: AIC, deduction: Deduction
    ) -> None:
        """Verify the *witness path*, never the text or discovery algorithm.

        Each premise must identify exactly one candidate node. The ordered
        nodes encode STRONG/WEAK/... alternating links. Every link is rebuilt
        from the current Sudoku candidate state, independently of AIC DFS.
        """
        if deduction.technique != technique.name:
            raise ValueError("Unexpected AIC technique name")
        if len(deduction.premises) < 4:
            raise ValueError("AIC witness is too short")
        path = []
        for p in deduction.premises:
            if len(p.cells) != 1 or len(p.digits) != 1:
                raise ValueError("Every AIC premise must identify one candidate")
            path.append(CandidateNode(*p.cells[0], next(iter(p.digits))))
        closed = path[0] == path[-1]
        if len(set(path[:-1] if closed else path)) != (len(path) - 1 if closed else len(path)):
            raise ValueError("AIC path repeats a node")
        num_links = len(path) - 1
        if (num_links < 3 or num_links > technique.max_links + (closed and num_links % 2 == 0)):
            raise ValueError("AIC path length exceeds the configured limit")
        graph = InferenceGraph(state)
        for index, (a, b) in enumerate(zip(path, path[1:])):
            kind = "strong" if index % 2 == 0 else "weak"
            if not graph.linked(a, b, kind):
                raise ValueError(f"Invalid AIC {kind} link at index {index}")

        if deduction.placements:
            if (not closed or num_links % 2 != 1 or deduction.eliminations
                    or deduction.placements != (Placement(path[0].cell, path[0].digit),)):
                raise ValueError("AIC strong discontinuity must place the repeated endpoint")
            return

        if not deduction.eliminations:
            raise ValueError("AIC must have a placement or elimination")
        if closed:
            if num_links % 2 != 0 or num_links < 4:
                raise ValueError("Continuous AIC must close on a weak link")
            permitted = set()
            excluded = set(path)
            for i in range(1, len(path)):
                if (i - 1) % 2 == 1:
                    permitted.update(graph.common_weak_neighbors(path[i - 1], path[i]) - excluded)
        else:
            if num_links % 2 != 1:
                raise ValueError("Open AIC must start and end with strong links")
            permitted = set(graph.common_weak_neighbors(path[0], path[-1]) - set(path))
        if any(CandidateNode(*effect.cell, effect.digit) not in permitted
               for effect in deduction.eliminations):
            raise ValueError("AIC elimination does not follow from its witness")

    @staticmethod
    def _verify_als_chain(
        state: CandidateState, technique: ALSChain, deduction: Deduction
    ) -> None:
        """Validate the supplied ALSs, RCCs, terminal digit and each target.

        This is independent of the chain discovery DFS; neither free-form
        explanation text nor cached discovery results are trusted.
        """
        if (deduction.technique != technique.name or deduction.placements
                or not deduction.eliminations):
            raise ValueError("Unexpected ALS-Chain deduction shape")
        premises = deduction.premises
        if (len(premises) < 6 or len(premises) % 2 != 0):
            raise ValueError("ALS-Chain requires alternating ALS/RCC witnesses")
        count = len(premises) // 2
        if not 3 <= count <= technique.max_sets:
            raise ValueError("ALS-Chain length is unsupported")
        group_premises = premises[:-1:2]
        link_premises = premises[1:-1:2]
        terminal_premise = premises[-1]
        if len(group_premises) != count or len(link_premises) != count - 1:
            raise ValueError("ALS-Chain witness is incomplete")
        seen: set[tuple[int, int]] = set()
        for group in group_premises:
            if (not 1 <= len(group.cells) <= technique.max_als_size
                    or seen.intersection(group.cells)
                    or not is_als(state, group.cells)
                    or group.digits != _candidate_union(state, group.cells)):
                raise ValueError("Invalid or overlapping ALS in chain")
            seen.update(group.cells)
        links: list[int] = []
        for i, link in enumerate(link_premises):
            if len(link.digits) != 1:
                raise ValueError("RCC link must have one digit")
            x = next(iter(link.digits))
            a = group_premises[i]
            b = group_premises[i + 1]
            if x not in a.digits or x not in b.digits:
                raise ValueError("RCC digit is not shared")
            if links and links[-1] == x:
                raise ValueError("Adjacent RCC digits must differ")
            left = tuple(cell for cell in a.cells if x in state.candidates_at(*cell))
            right = tuple(cell for cell in b.cells if x in state.candidates_at(*cell))
            if (not left or not right
                    or tuple(sorted((*left, *right))) != link.cells
                    or not all(_sees(l, r) for l in left for r in right)):
                raise ValueError("RCC positions or visibility are invalid")
            links.append(x)
        if (terminal_premise.cells or len(terminal_premise.digits) != 1
                or len({effect.digit for effect in deduction.eliminations}) != 1):
            raise ValueError("ALS-Chain terminal digit is ambiguous")
        z = next(iter(terminal_premise.digits))
        if (z not in group_premises[0].digits
                or z not in group_premises[-1].digits
                or z in (links[0], links[-1])
                or any(effect.digit != z for effect in deduction.eliminations)):
            raise ValueError("Invalid ALS-Chain terminal candidate")
        # Independently compute the permitted elimination locations.
        end_cells = (group_premises[0].cells, group_premises[-1].cells)
        holders = tuple(cell for group in end_cells for cell in group
                        if z in state.candidates_at(*cell))
        for effect in deduction.eliminations:
            if (effect.cell in seen
                    or z not in state.candidates_at(*effect.cell)
                    or not all(_sees(effect.cell, cell) for cell in holders)):
                raise ValueError("ALS-Chain elimination is not justified")

    @staticmethod
    def _verify_als_xz(
        state: CandidateState, technique: ALSXZ, deduction: Deduction
    ) -> None:
        """Independently validate two disjoint ALSs, their RCC and all Z targets."""
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 3 or not deduction.eliminations):
            raise ValueError("Unexpected ALS-XZ deduction structure")
        first, second, link = deduction.premises
        a, b = first.cells, second.cells
        if (len(a) > technique.max_size or len(b) > technique.max_size
                or not set(a).isdisjoint(b) or not is_als(state, a) or not is_als(state, b)
                or first.digits != _candidate_union(state, a)
                or second.digits != _candidate_union(state, b)):
            raise ValueError("ALS-XZ witness does not contain two valid disjoint ALSs")
        if len(link.digits) != 1:
            raise ValueError("ALS-XZ must identify a single restricted common candidate")
        x = next(iter(link.digits))
        if x not in first.digits & second.digits:
            raise ValueError("Invalid ALS-XZ restricted common candidate")
        x_a = tuple(cell for cell in a if x in state.candidates_at(*cell))
        x_b = tuple(cell for cell in b if x in state.candidates_at(*cell))
        if (not x_a or not x_b
                or tuple(sorted((*x_a, *x_b))) != link.cells
                or not all(_sees(c, d) for c in x_a for d in x_b)):
            raise ValueError("Invalid ALS-XZ restricted common candidate or RCC positions")
        digits = {effect.digit for effect in deduction.eliminations}
        if len(digits) != 1:
            raise ValueError("ALS-XZ deduction must eliminate one shared digit")
        z = next(iter(digits))
        if z == x or z not in first.digits & second.digits:
            raise ValueError("ALS-XZ elimination digit must be shared and not the RCC")
        z_holders = tuple(cell for cell in (*a, *b) if z in state.candidates_at(*cell))
        for effect in deduction.eliminations:
            if (effect.cell in a or effect.cell in b
                    or effect.digit not in state.candidates_at(*effect.cell)
                    or not all(_sees(effect.cell, holder) for holder in z_holders)):
                raise ValueError("ALS-XZ elimination is not justified")

    @staticmethod
    def _verify_sue_de_coq(
        state: CandidateState, technique: SueDeCoq, deduction: Deduction
    ) -> None:
        """Check the exact sector partition and every affected cell/digit."""
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 3 or not deduction.eliminations):
            raise ValueError("Unexpected Sue de Coq deduction structure")
        intersection, line_als, box_als = deduction.premises
        cross, left, right = intersection.cells, line_als.cells, box_als.cells
        if (not 2 <= len(cross) <= 3 or len(set(cross)) != len(cross)
                or len(left) > technique.max_side_size
                or len(right) > technique.max_side_size
                or not is_als(state, left) or not is_als(state, right)):
            raise ValueError("Invalid Sue de Coq group sizes or side ALSs")
        v = _candidate_union(state, cross)
        vl = _candidate_union(state, left)
        vb = _candidate_union(state, right)
        if (intersection.digits != v or line_als.digits != vl or box_als.digits != vb
                or not vl <= v or not vb <= v or vl & vb
                or len(v) != len(cross) + len(left) + len(right)):
            raise ValueError("Invalid Sue de Coq disjoint candidate partition")
        from sudoku.solvers.logical.singles import _units
        rows_cols = [unit for kind, _, unit in _units() if kind != 'box']
        boxes = [unit for kind, _, unit in _units() if kind == 'box']
        groups = []
        for line in rows_cols:
            for box in boxes:
                crossing = set(line) & set(box)
                if (tuple(cell for cell in line if cell in crossing
                          and state.candidates_at(*cell)) == cross
                        and set(left) <= set(line) - crossing
                        and set(right) <= set(box) - crossing):
                    groups.append((line, box))
        if not groups:
            raise ValueError("Sue de Coq witness does not form a line/box intersection")
        leftover = v - vl - vb
        for effect in deduction.eliminations:
            if effect.digit not in state.candidates_at(*effect.cell):
                raise ValueError("Sue de Coq effect is not an available candidate")
            if not any(
                (effect.cell in line and effect.cell not in cross
                 and effect.cell not in left and effect.digit in vl | leftover)
                or
                (effect.cell in box and effect.cell not in cross
                 and effect.cell not in right and effect.digit in vb | leftover)
                for line, box in groups
            ):
                raise ValueError("Sue de Coq elimination is not justified")

    @staticmethod
    def _verify_subset(
        state: CandidateState, technique: LogicalTechnique, deduction: Deduction
    ) -> None:
        """Reconstruct the claimed subset and validate every proposed elimination."""
        if (deduction.technique != technique.name or deduction.placements
                or not deduction.eliminations or len(deduction.premises) != 1):
            raise ValueError("Unexpected deduction shape or technique name")
        premise = deduction.premises[0]
        size = technique.size
        if len(premise.cells) != size or len(premise.digits) != size:
            raise ValueError(f"Subset premise must identify {size} cells and {size} digits")
        cells = premise.cells
        digits = premise.digits
        board = state.board
        valid_units = []
        for _, _, unit in _units():
            if not set(cells).issubset(unit):
                continue
            if isinstance(technique, NakedSubset):
                if not all(0 < len(state.candidates_at(*cell)) <= size for cell in cells):
                    continue
                union = frozenset().union(*(state.candidates_at(*cell) for cell in cells))
                if union != digits:
                    continue
                if any(cell not in cells and state.candidates_at(*cell) and
                       state.candidates_at(*cell) <= digits for cell in unit):
                    continue
            else:
                placed = {board.value_at(*cell) for cell in unit} - {0}
                if digits & placed:
                    continue
                positions = {
                    cell for cell in unit
                    if any(digit in state.candidates_at(*cell) for digit in digits)
                }
                if positions != set(cells):
                    continue
                if any(not any(digit in state.candidates_at(*cell) for cell in cells)
                       for digit in digits):
                    continue
            valid_units.append(unit)
        if not valid_units:
            raise ValueError("Invalid pair premise" if size == 2 else "Invalid subset premise")
        for elimination in deduction.eliminations:
            if elimination.digit not in state.candidates_at(*elimination.cell):
                raise ValueError("Elimination is not an available candidate")
            if isinstance(technique, NakedSubset):
                permitted = (elimination.cell not in cells and elimination.digit in digits
                             and any(elimination.cell in unit for unit in valid_units))
            else:
                permitted = elimination.cell in cells and elimination.digit not in digits
            if not permitted:
                raise ValueError("Elimination is not justified by the subset")

    @staticmethod
    def _verify_pattern(state: CandidateState, technique: LogicalTechnique, deduction: Deduction) -> None:
        """Recompute exact valid effects from the current state; reject forged moves.

        The standard grouping branch is equivalent to validated naked subsets.
        Premise prose is not a formal certificate.
        """
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected deduction shape")
        if isinstance(technique, LockedCandidates):
            valid = [ (positions,digit,effects) for positions,digit,effects,_
                      in _locked_patterns(state,technique.mode) ]
            if not any(deduction.premises[0].cells == positions
                       and deduction.premises[0].digits == frozenset({digit})
                       and set(deduction.eliminations).issubset(effects)
                       for positions,digit,effects in valid):
                raise ValueError("Locked candidates elimination is not justified")
        else:
            # Group partition is merely an alternate presentation of a naked subset.
            premise=deduction.premises[0]
            valid=[]
            for size in (2,3,4):
                for subset in NakedSubset(size).find_deductions(state):
                    p=subset.premises[0]
                    if p.cells==premise.cells and p.digits==premise.digits:
                        valid.append(subset)
            if not any(set(deduction.eliminations).issubset(subset.eliminations)
                       for subset in valid):
                raise ValueError("Disjoint groups elimination is not justified")

    @staticmethod
    def _verify_fish(state: CandidateState, technique: BasicFish, deduction: Deduction) -> None:
        """Check supplied fish geometry directly; never rerun fish detection."""
        verify_basic_fish(state, deduction, name=technique.name, size=technique.size)

    @staticmethod
    def _verify_finned_fish(state: CandidateState, technique: LogicalTechnique, deduction: Deduction) -> None:
        """Check the claimed finned-fish witness without pattern discovery."""
        if isinstance(technique, FinnedXWing):
            verify_finned_xwing(state, deduction, name=technique.name)
        else:
            verify_general_finned_fish(
                state, deduction, name=technique.name, size=technique.size
            )

    @staticmethod
    def _verify_strong_links(
        state: CandidateState, technique: LogicalTechnique, deduction: Deduction
    ) -> None:
        """Reconstruct the conjugate links and test every proposed elimination."""
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected strong-link deduction shape")
        premise = deduction.premises[0]
        if len(premise.digits) != 1 or len(premise.cells) != 4:
            raise ValueError("Invalid strong-link premise")
        for digit, chain, effects in _strong_link_patterns(state, technique.name):
            if (premise.digits == frozenset({digit})
                    and (premise.cells == chain or premise.cells == chain[::-1])
                    and set(deduction.eliminations).issubset(effects)):
                return
        raise ValueError("Strong-link elimination is not justified")

    @staticmethod
    def _verify_wings(
        state: CandidateState, technique: LogicalTechnique, deduction: Deduction
    ) -> None:
        """Check pattern geometry and each proposed elimination against candidate state."""
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected wing deduction shape")
        premise = deduction.premises[0]
        for cells, digits, effects, _ in _wing_patterns(state, technique.name):
            if (premise.cells == cells and premise.digits == digits
                    and set(deduction.eliminations).issubset(effects)):
                return
        raise ValueError("Wing elimination is not justified")

    @staticmethod
    def _verify_new_patterns(state: CandidateState, technique: LogicalTechnique, deduction: Deduction) -> None:
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected rectangle/finned fish deduction structure")
        patterns = (_empty_rectangle_patterns(state) if isinstance(technique, EmptyRectangle)
                    else _UNIQUE_RECTANGLE_PATTERNS[technique._type](state) if isinstance(technique, (UniqueRectangleType2, UniqueRectangleType3, UniqueRectangleType4, UniqueRectangleType5, UniqueRectangleType6))
                    else _UNIQUE_RECTANGLE_PATTERNS[1](state) if isinstance(technique, UniqueRectangleType1)
                    else _hidden_rectangle_patterns(state))
        premise = deduction.premises[0]
        for cells, digits, effects, _ in patterns:
            if (premise.cells == cells and premise.digits == digits
                    and set(deduction.eliminations).issubset(effects)):
                return
        raise ValueError("Unjustified rectangle/finned fish deduction")

    @staticmethod
    def _verify_simple_coloring(
        state: CandidateState, technique: SimpleColoring, deduction: Deduction
    ) -> None:
        """Independently reconstruct coloring and validate each elimination.

        The supplied description is not treated as mathematical evidence.
        An effect must be supported by one complete, bipartite component
        through either a wrap on one color or a trap outside the component.
        """
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected Simple Coloring deduction structure")
        premise = deduction.premises[0]
        if len(premise.digits) != 1:
            raise ValueError("Coloring must identify exactly one digit")
        digit = next(iter(premise.digits))
        proposed = set(deduction.eliminations)
        for component in _colored_components(state, digit):
            if premise.cells != component.cells:
                continue
            allowed = (
                _wrap_effects(state, component, 0),
                _wrap_effects(state, component, 1),
                _trap_effects(state, component),
            )
            if any(effects and proposed.issubset(set(effects)) for effects in allowed):
                return
        raise ValueError("Simple Coloring elimination is not justified")

    @staticmethod
    def _verify_x_chain(
        state: CandidateState, technique: XChain, deduction: Deduction
    ) -> None:
        """Independently validate every link, endpoint and elimination.

        Checks the candidate graph directly instead of relying on the
        discovery routine or trusting the premise description.
        """
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected X-Chain deduction structure")
        premise = deduction.premises[0]
        cells = premise.cells
        if (len(premise.digits) != 1 or len(cells) < 4
                or len(cells) % 2 != 0 or len(cells) - 1 > technique.max_links
                or len(set(cells)) != len(cells)):
            raise ValueError("Invalid X-Chain witness")
        digit = next(iter(premise.digits))
        strong, weak = _chain_graph(state, digit)
        if any(cell not in strong for cell in cells):
            raise ValueError("X-Chain contains an absent candidate")
        for i, (left, right) in enumerate(zip(cells, cells[1:])):
            neighbors = strong[left] if i % 2 == 0 else weak[left]
            if right not in neighbors:
                raise ValueError("X-Chain strong/weak alternation is not justified")
        allowed = set(_chain_eliminations(state, digit, cells))
        if not set(deduction.eliminations).issubset(allowed):
            raise ValueError("X-Chain elimination is not justified")

    @staticmethod
    def _verify_xy_chain(
        state: CandidateState, technique: XYChain, deduction: Deduction
    ) -> None:
        """Recheck the full bivalue implication path against the live state.

        This checks the *claimed* path directly rather than calling the
        discovery routine or trusting the human-readable premise.
        """
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected XY-Chain deduction structure")
        premise = deduction.premises[0]
        chain = premise.cells
        if (len(premise.digits) != 1
                or not technique.min_cells <= len(chain) <= technique.max_cells
                or len(set(chain)) != len(chain)):
            raise ValueError("Invalid XY-Chain witness")
        digit = next(iter(premise.digits))
        pairs = [state.candidates_at(*cell) for cell in chain]
        if any(len(pair) != 2 for pair in pairs):
            raise ValueError("XY-Chain must consist of bivalue cells")
        if digit not in pairs[0] or digit not in pairs[-1]:
            raise ValueError("XY-Chain endpoint digit is unavailable")
        # Assuming the first endpoint != digit, its *other* value is true.
        # Each inter-cell peer link then excludes that value in the next
        # bivalue cell, forcing its other candidate to be true, etc.
        forced = next(iter(pairs[0] - {digit}))
        for i in range(1, len(chain)):
            if not _sees(chain[i - 1], chain[i]) or forced not in pairs[i]:
                raise ValueError("XY-Chain implication link is invalid")
            forced = next(iter(pairs[i] - {forced}))
        if forced != digit:
            raise ValueError("XY-Chain does not force the endpoint digit")
        allowed = set(_xy_chain_eliminations(state, digit, chain))
        if not set(deduction.eliminations).issubset(allowed):
            raise ValueError("XY-Chain elimination is not justified")

    @staticmethod
    def _verify_remote_pairs(
        state: CandidateState, technique: RemotePairs, deduction: Deduction
    ) -> None:
        """Verify every link and target directly, without trusting descriptions."""
        if (deduction.technique != technique.name or deduction.placements
                or len(deduction.premises) != 1 or not deduction.eliminations):
            raise ValueError("Unexpected Remote Pairs deduction structure")
        premise = deduction.premises[0]
        chain, pair = premise.cells, premise.digits
        if (len(pair) != 2 or len(chain) < 4 or len(chain) % 2
                or len(set(chain)) != len(chain)):
            raise ValueError("Invalid Remote Pairs chain shape")
        if not all(state.candidates_at(*cell) == pair for cell in chain):
            raise ValueError("Remote Pairs chain must have identical bivalue cells")
        if not all(_sees(a, b) for a, b in zip(chain, chain[1:])):
            raise ValueError("Remote Pairs consecutive cells must see one another")
        start, end = chain[0], chain[-1]
        if _sees(start, end):
            raise ValueError("Remote Pairs endpoints must not form a Naked Pair")
        # Only accept a consistent, bipartite connected component containing
        # the entire proposed chain. A contradictory odd-cycle is not a proof.
        components = (
            comp for comp in _pair_components(state)
            if comp.pair == pair and set(chain).issubset(comp.cells)
        )
        component = next(components, None)
        if component is None:
            raise ValueError("Remote Pairs chain is not in a valid bivalue component")
        colors = dict(component.colors)
        if colors[start] == colors[end]:
            raise ValueError("Remote Pairs endpoints must have opposite parity")
        for effect in deduction.eliminations:
            if (effect.digit not in pair
                    or effect.digit not in state.candidates_at(*effect.cell)
                    or effect.cell in component.cells
                    or not _sees(effect.cell, start)
                    or not _sees(effect.cell, end)):
                raise ValueError("Remote Pairs elimination is not justified")

    @staticmethod
    def _verify_bug_plus_one(
        state: CandidateState, technique: BUGPlusOne, deduction: Deduction
    ) -> None:
        """Recheck the global BUG parity condition before accepting a placement."""
        if (deduction.technique != technique.name or deduction.eliminations
                or len(deduction.premises) != 1 or len(deduction.placements) != 1):
            raise ValueError("Unexpected BUG+1 deduction structure")

        premise = deduction.premises[0]
        placement = deduction.placements[0]
        if (premise.cells != (placement.cell,)
                or premise.digits != frozenset({placement.digit})
                or (placement.cell, placement.digit) not in _bug_plus_one_patterns(state)):
            raise ValueError("BUG+1 placement is not justified by the candidate state")
