"""
Experiment runners (configurations B0-B7).

Each configuration is a factorial cell of the study:

    code  retrieval        multi-agent  SCV
    B0    none             no           built-in rule check
    B1    none             no           no
    B2    vector           no           no
    B3    graph            no           no
    B4    vector           yes          no
    B5    constraint-aware yes          no
    B6    vector           yes          yes
    B7    constraint-aware yes          yes

The runners are thin subclasses of :class:`BaseRunner` so that the only
difference between two cells is the configuration tuple — the pipeline itself
is identical, which is exactly what the factorial design requires.
"""
from .base import BaseRunner, RunOutcome
from .registry import RUNNER_MATRIX, get_runner

__all__ = ['BaseRunner', 'RunOutcome', 'get_runner', 'RUNNER_MATRIX']
