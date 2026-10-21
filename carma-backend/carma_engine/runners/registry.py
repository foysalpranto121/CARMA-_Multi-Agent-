"""
Runner registry — maps a configuration code to its runner class.

The matrix is the single source of truth for the factorial design and is
exported so that the API can render it and the tests can assert it.
"""
from __future__ import annotations

from .b0_rule_based import B0RuleBasedRunner
from .b1_single_llm import B1SingleLLMRunner
from .b2_vector_rag import B2VectorRAGRunner
from .b3_graph_rag import B3GraphRAGRunner
from .b4_mas_vector import B4MASVectorRunner
from .b5_mas_car import B5MASCARRunner
from .b6_mas_scv import B6MASSCVRunner
from .b7_carma import B7CARMARunner

RUNNER_MATRIX = {
    'B0': B0RuleBasedRunner,
    'B1': B1SingleLLMRunner,
    'B2': B2VectorRAGRunner,
    'B3': B3GraphRAGRunner,
    'B4': B4MASVectorRunner,
    'B5': B5MASCARRunner,
    'B6': B6MASSCVRunner,
    'B7': B7CARMARunner,
}


def get_runner(code: str, config=None, seed=None, llm=None):
    """
    Instantiate the runner of a configuration code.

    :param code:   configuration code (``B0`` … ``B7``)
    :param config: the ``RunConfiguration`` of the run
    :param seed:   the random seed of the run (reproducibility)
    :param llm:    an optional pre-built LLM client
    :raises KeyError: when the code is not part of the B0-B7 matrix.
    """
    try:
        runner_class = RUNNER_MATRIX[str(code).upper()]
    except KeyError as exc:
        raise KeyError(f'Unknown configuration code "{code}". '
                       f'Expected one of {sorted(RUNNER_MATRIX)}.') from exc
    return runner_class(config=config, llm=llm, seed=seed)
