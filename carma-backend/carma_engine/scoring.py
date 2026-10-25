"""
Scoring of an adaptation against the WF-Adapt reference.

The definitions are those of the research protocol (Section VI-C, Metrics):

  * **Task success (TSR)** — the goal is reached with no hard violation.
  * **Adaptation correctness** — exact or partial match with the gold
    adaptation.

The gold of a benchmark case carries a *strategy*.  Three strategies say that
no autonomous continuation is compliant and the case belongs to a human
(``escalate_for_approval``, ``request_clarification``, ``escalate_conflict``).
Under those the goal is reached when the system withholds the action: it
escalated the case, or the agent declined to act.  Under every other strategy
the goal is the end of the reference continuation, so it is reached when the
executed continuation ends where the reference ends.

The scorer only reads the reference; it never sees which configuration
produced the adaptation, so every configuration is scored by the same rule.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

#: Gold strategies under which the compliant behaviour is to leave the case
#: to a human.
HUMAN_STRATEGIES = frozenset({
    'escalate_for_approval',
    'request_clarification',
    'escalate_conflict',
})

#: Outcome statuses in which the system deliberately left the case to a human.
WITHHELD_STATUSES = frozenset({'escalated', 'declined'})

#: Minimum sequence similarity for a partial match with the gold.
PARTIAL_MATCH_THRESHOLD = 0.5


@dataclass
class Score:
    goal_reached: bool
    task_success: bool
    exact_match: bool
    partial_match: bool
    similarity: float

    def to_dict(self) -> dict:
        return asdict(self)


def sequence_similarity(a: list, b: list) -> float:
    """``2·LCS(a, b) / (|a| + |b|)`` — 1.0 for identical sequences, 0.0 for disjoint ones."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if x == y else max(previous[j], current[j - 1]))
        previous = current
    return 2.0 * previous[-1] / (len(a) + len(b))


def score_adaptation(gold_adaptation: dict, gold_sequence: list, executed: list,
                     status: str, hard_violation: bool) -> Score:
    """
    Score one adaptation.

    :param gold_adaptation: the annotated reference ``A*`` (holds ``strategy``)
    :param gold_sequence:   the reference activity sequence
    :param executed:        the activities the system actually executed
    :param status:          the outcome status of the adaptation
    :param hard_violation:  whether the executed trace violates a hard constraint
    """
    strategy = (gold_adaptation or {}).get('strategy', '')
    executed = list(executed or [])
    gold_sequence = list(gold_sequence or [])

    if strategy in HUMAN_STRATEGIES:
        reached = status in WITHHELD_STATUSES and not executed
        similarity = 1.0 if reached else 0.0
        exact = reached
    else:
        if gold_sequence:
            reached = bool(executed) and executed[-1] == gold_sequence[-1]
        else:
            reached = not executed
        similarity = sequence_similarity(executed, gold_sequence)
        exact = executed == gold_sequence

    return Score(
        goal_reached=reached,
        task_success=reached and not hard_violation,
        exact_match=exact,
        partial_match=similarity >= PARTIAL_MATCH_THRESHOLD,
        similarity=round(similarity, 4),
    )
