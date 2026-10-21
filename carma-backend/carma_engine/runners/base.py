"""
Base runner — the shared CARMA pipeline for one benchmark case.

    constraint graph → state estimation → retrieval → agent team
                     → symbolic verification → cost/metric computation

The runner is deterministic given ``(case, configuration)``: the only source
of randomness is the LLM, and its sampling parameters (temperature, seed) come
from the run configuration.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..agents.planner import summarize_evidence
from ..constraint_knowledge.graph_builder import build_constraint_graph
from ..escalation.gate import TAU_DEFAULT, should_escalate
from ..llm.client import LLMUnavailable, build_llm
from ..retriever.constraint_aware import ConstraintAwareRetriever, plain_vector_rag
from ..state_estimator.replay import estimate_state
from ..verifier.symbolic import SCVVerifier

log = logging.getLogger('carma')

AGENT_ROLES = ('planner', 'critic', 'executor', 'policy_auditor')


@dataclass
class RunOutcome:
    """The result of running one case under one configuration."""
    plan: dict = field(default_factory=dict)
    plan_id: str = ''
    activity_seq: list = field(default_factory=list)
    confidence: float | None = None
    exec_cost: float = 0.0
    viol_cost: float = 0.0
    task_success: bool = False
    conformance_fitness: float = 0.0
    repair_rounds: int = 0
    status: str = 'failed'
    needs_escalation: bool = False
    escalation_reason: str = ''
    tokens_used: int = 0
    llm_calls: int = 0
    retrieved_docs: list = field(default_factory=list)
    retrieval_scores: dict = field(default_factory=dict)
    scv_approved: bool | None = None
    scv_token: str = ''
    violation_report: dict = field(default_factory=dict)
    error: str = ''

    def to_dict(self) -> dict:
        return {
            'plan': self.plan,
            'plan_id': self.plan_id,
            'activity_seq': self.activity_seq,
            'confidence': self.confidence,
            'exec_cost': self.exec_cost,
            'viol_cost': self.viol_cost,
            'task_success': self.task_success,
            'conformance_fitness': self.conformance_fitness,
            'repair_rounds': self.repair_rounds,
            'status': self.status,
            'needs_escalation': self.needs_escalation,
            'escalation_reason': self.escalation_reason,
            'tokens_used': self.tokens_used,
            'llm_calls': self.llm_calls,
            'retrieved_docs': self.retrieved_docs,
            'retrieval_scores': self.retrieval_scores,
            'scv_approved': self.scv_approved,
            'scv_token': self.scv_token,
            'violation_report': self.violation_report,
            'error': self.error,
        }


def _executed_prefix(benchmark_case) -> list:
    """
    The prefix of a benchmark case that has already been executed.

    A benchmark case carries the executed part of the log case it is built
    on; the agent has to produce the continuation of that prefix.
    """
    prefix = getattr(benchmark_case, 'prefix_trace', None)
    if prefix:
        return prefix
    return benchmark_case.case.prefix_trace or []


class BaseRunner:
    """
    Shared implementation of one experiment configuration.

    :param code:           configuration code (``B0`` .. ``B7``)
    :param retrieval_type: ``none`` | ``vector`` | ``graph`` | ``constraint_aware``
    :param multi_agent:    use the 4-role agent team instead of a single agent
    :param use_scv:        run the symbolic constraint verifier
    :param num_agents:     number of specialist agents
    """

    code = 'B0'
    retrieval_type = 'none'
    multi_agent = False
    use_scv = False
    num_agents = 1

    def __init__(self, config=None, llm=None, seed=None):
        self.config = config
        self.seed = seed if seed is not None else getattr(config, 'seed', None)
        self._llm = llm

    # ── LLM ───────────────────────────────────────────────────
    def llm(self):
        if self._llm is None:
            model = getattr(self.config, 'llm_model', 'gpt-4o')
            temperature = float(getattr(self.config, 'temperature', 0.0) or 0.0)
            max_tokens = int(getattr(self.config, 'max_tokens', 4096) or 4096)
            self._llm = build_llm(model=model, temperature=temperature,
                                  max_tokens=max_tokens, seed=self.seed)
        return self._llm

    def tau(self) -> float:
        """Confidence threshold for human escalation."""
        value = getattr(self.config, 'tau_threshold', None)
        if value is None:
            return TAU_DEFAULT
        try:
            return float(value)
        except (TypeError, ValueError):
            return TAU_DEFAULT

    def repair_rounds(self) -> int:
        value = getattr(self.config, 'k_repair_rounds', None)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 3

    # ── pipeline steps ────────────────────────────────────────
    def build_graph(self, benchmark_case):
        """Compile the constraint graph of the case's process."""
        from ..constraint_knowledge.graph_builder import apply_scenario_frame

        process = benchmark_case.process
        constraint_set = benchmark_case.constraint_set
        sets = [constraint_set] if constraint_set is not None else None
        graph = build_constraint_graph(process, constraint_sets=sets)
        # The perturbation can change the frame of the case: a withdrawn
        # activity, a new rule version or a renamed activity.  The frame
        # has to know about it, or the verifier would reject the very
        # behaviour the scenario asks for.
        return apply_scenario_frame(graph, benchmark_case.perturbation or {})

    def estimate(self, benchmark_case, constraint_graph):
        """Estimate the process state reached by the case's prefix trace."""
        prefix = _executed_prefix(benchmark_case)
        case_timestamp = _last_timestamp(prefix)
        return estimate_state(prefix, benchmark_case.process,
                              constraint_graph=constraint_graph,
                              case_timestamp=case_timestamp)

    def retrieve(self, benchmark_case, state, constraint_graph):
        """Retrieve the evidence pack according to the configuration."""
        process_id = str(benchmark_case.process_id)
        query = _build_query(benchmark_case)

        if self.retrieval_type == 'constraint_aware':
            retriever = ConstraintAwareRetriever(
                alpha=float(getattr(self.config, 'alpha', 0.6) or 0.6),
                beta=float(getattr(self.config, 'beta', 0.2) or 0.2),
                gamma=float(getattr(self.config, 'gamma', 0.2) or 0.2),
                process_id=process_id,
            )
            docs = retriever.retrieve(query, state, constraint_graph,
                                      case_timestamp=state.case_timestamp,
                                      process_id=process_id,
                                      k=int(getattr(self.config, 'top_k', 10) or 10))
        elif self.retrieval_type == 'vector':
            docs = plain_vector_rag(process_id, query,
                                    k=int(getattr(self.config, 'top_k', 10) or 10))
        elif self.retrieval_type == 'graph':
            docs = self._graph_retrieval(process_id, query, state, constraint_graph)
        else:
            docs = []

        scores = {doc.get('provenance_id') or doc.get('id'): doc.get('score')
                  for doc in docs}
        return docs, scores

    def _graph_retrieval(self, process_id: str, query: str, state, constraint_graph) -> list[dict]:
        """
        GraphRAG baseline: documents are selected by graph proximity to the
        current node instead of by dense similarity.
        """
        from ..retriever.scorer import graph_proximity  # noqa: PLC0415

        retriever = ConstraintAwareRetriever(process_id=process_id)
        candidates = retriever._candidates(process_id, query)
        scored = []
        for candidate in candidates:
            proximity = graph_proximity(
                constraint_graph, state.current_node,
                candidate['payload'].get('activity_tags') or [])
            scored.append({
                'id': candidate['id'],
                'payload': candidate['payload'],
                'score': proximity,
                'similarity': proximity,
                'provenance_id': f"PRV-{str(candidate['id'])[:8].upper()}",
            })
        scored.sort(key=lambda item: item['score'], reverse=True)
        return scored[:int(getattr(self.config, 'top_k', 10) or 10)]

    def agent_roles(self) -> list[str]:
        if not self.multi_agent:
            return []
        count = max(1, int(getattr(self.config, 'num_agents', 4) or 4))
        return list(AGENT_ROLES[:count])

    def plan_case(self, benchmark_case, state, constraint_graph, evidence):
        """Produce the adaptation plan (overridden by the rule-based runner)."""
        from ..agents.graph import build_agent_graph  # noqa: PLC0415

        llm = self.llm()
        graph = build_agent_graph(
            llm=llm,
            config=self.config,
            tau=self.tau(),
            agent_roles=self.agent_roles(),
            repair_rounds=self.repair_rounds(),
        )
        initial_state = {
            'perturbation': benchmark_case.perturbation or {},
            'prefix_trace': _executed_prefix(benchmark_case),
            'process_state': state.to_dict(),
            'evidence': evidence,
            'constraint_graph_data': {},
            'plan': None,
            'violation_report': None,
            'scv_passed': False,
            'repair_round': 0,
            'escalate': False,
            'escalation_reason': '',
            'messages': [],
            'token_counts': {'input': 0, 'output': 0},
            'llm_calls': 0,
            'agent_intents': [],
            'result': {},
            'extras': {},
        }
        try:
            final_state = graph.invoke(initial_state)
        except Exception as exc:
            log.warning('Agent graph failed (%s) — falling back to heuristic plan.', exc)
            final_state = initial_state

        plan = final_state.get('plan') or {}
        extras = final_state.get('extras') or {}
        executor = extras.get('executor') or {}
        critic = extras.get('critic') or {}
        return {
            'plan': plan,
            'plan_id': plan.get('plan_id', ''),
            'activity_seq': executor.get('activity_seq') or [],
            'confidence': critic.get('confidence', plan.get('confidence')),
            'exec_cost': executor.get('exec_cost', 0.0),
            'task_success': bool(executor.get('task_success')),
            'repair_rounds': int(final_state.get('repair_round', 0) or 0),
            'escalate': bool(final_state.get('escalate')),
            'escalation_reason': final_state.get('escalation_reason', ''),
            'llm_calls': int(final_state.get('llm_calls', 0) or 0),
            'agent_intents': final_state.get('agent_intents') or [],
        }

    def verify(self, benchmark_case, plan, constraint_graph, state, agent_intents=None):
        """
        Run the symbolic constraint verifier.

        The verifier is the *yardstick* of the study: it scores every
        adaptation, whatever the configuration is, so that the violation
        rate of two configurations can be compared.  Whether the verdict
        is also *acted upon* — the plan is blocked, repaired or escalated
        — is what the ``use_scv`` switch of a configuration decides.

        :returns: ``(passed, token, violation_cost, report)``
        """
        verifier = SCVVerifier(constraint_set=benchmark_case.constraint_set)
        passed, token, cost, report = verifier.verify(
            plan=plan,
            prefix_trace=_executed_prefix(benchmark_case),
            process=benchmark_case.process,
            constraint_graph=constraint_graph,
            all_agent_intents=agent_intents,
        )
        return passed, token or '', cost, report

    # ── main entry point ──────────────────────────────────────
    def run(self, benchmark_case, config=None) -> dict:
        """
        Run one benchmark case under this configuration.

        :returns: a dict matching :class:`RunOutcome`.
        """
        outcome = RunOutcome()
        started = time.monotonic()

        try:
            constraint_graph = self.build_graph(benchmark_case)
            state = self.estimate(benchmark_case, constraint_graph)
            evidence, scores = self.retrieve(benchmark_case, state, constraint_graph)
            outcome.retrieved_docs = [
                {
                    'doc_id': doc.get('id'),
                    'provenance_id': doc.get('provenance_id'),
                    'score': doc.get('score'),
                    'title': (doc.get('payload') or {}).get('title'),
                }
                for doc in evidence
            ]
            outcome.retrieval_scores = scores

            agent_result = self.plan_case(benchmark_case, state, constraint_graph, evidence)
            outcome.plan = agent_result.get('plan') or {}
            outcome.plan_id = agent_result.get('plan_id', '')
            outcome.activity_seq = agent_result.get('activity_seq') or []
            outcome.confidence = agent_result.get('confidence')
            outcome.exec_cost = float(agent_result.get('exec_cost') or 0.0)
            outcome.repair_rounds = int(agent_result.get('repair_rounds') or 0)
            outcome.llm_calls = int(agent_result.get('llm_calls') or 0)

            passed, token, viol_cost, report = self.verify(
                benchmark_case, outcome.plan, constraint_graph, state,
                agent_intents=agent_result.get('agent_intents'))
            outcome.scv_approved = passed
            outcome.scv_token = token
            outcome.viol_cost = viol_cost
            outcome.violation_report = report
            if self.use_scv and not passed:
                # The pre-execution verifier is part of the agent's loop
                # in this configuration: a plan that violates the frame is
                # not executed.
                outcome.activity_seq = []
                outcome.task_success = False

            outcome.conformance_fitness = _conformance_fitness(
                outcome.viol_cost, constraint_graph)
            if outcome.task_success is False and outcome.scv_approved is not False:
                outcome.task_success = bool(outcome.activity_seq)

            escalate, reason = should_escalate(
                outcome.plan,
                verdict={'violation_report': outcome.violation_report} if outcome.violation_report else None,
                constraint_graph=constraint_graph,
                tau=self.tau(),
                repair_rounds=outcome.repair_rounds,
                max_repair_rounds=self.repair_rounds(),
                escalate_flag=agent_result.get('escalate', False),
            )
            outcome.needs_escalation = escalate
            outcome.escalation_reason = reason or agent_result.get('escalation_reason', '')

            if escalate:
                outcome.status = 'escalated'
            elif outcome.viol_cost > 0:
                outcome.status = 'violation'
            elif outcome.repair_rounds:
                outcome.status = 'repair'
            else:
                outcome.status = 'success'

            llm = self._llm
            if llm is not None:
                outcome.tokens_used = llm.usage.total_tokens
                outcome.llm_calls = max(outcome.llm_calls, llm.usage.calls)

        except LLMUnavailable as exc:
            outcome.status = 'failed'
            outcome.error = str(exc)
            log.warning('LLM unavailable for case %s: %s', getattr(benchmark_case, 'id', '?'), exc)
        except Exception as exc:
            outcome.status = 'failed'
            outcome.error = str(exc)
            log.exception('Runner %s failed: %s', self.code, exc)

        outcome_dict = outcome.to_dict()
        outcome_dict['latency_s'] = time.monotonic() - started
        return outcome_dict


# ── helpers ───────────────────────────────────────────────────
def _last_timestamp(prefix: list):
    for event in reversed(prefix or []):
        timestamp = event.get('timestamp')
        if timestamp:
            return timestamp
    return None


def _build_query(benchmark_case) -> str:
    perturbation = benchmark_case.perturbation or {}
    text = perturbation.get('description') or benchmark_case.perturbation_text or ''
    if not text:
        text = ' '.join(str(value) for value in perturbation.values() if isinstance(value, str))
    activities = ' '.join(
        event.get('activity', '') for event in (_executed_prefix(benchmark_case))[-5:])
    return f'{text} {activities}'.strip()


def _conformance_fitness(violation_cost: float, constraint_graph) -> float:
    """
    Normalised conformance fitness in ``[0, 1]``.

    ``1 - violation_cost / total_active_constraint_budget`` — 1.0 when no
    constraint is violated, 0.0 when the full budget is exhausted.
    """
    if constraint_graph is None:
        return 1.0 if not violation_cost else 0.0
    budget = sum(float(data.get('violation_cost', 1.0) or 0.0)
                 for _, data in constraint_graph.nodes(data=True))
    if budget <= 0:
        return 1.0 if not violation_cost else 0.0
    return max(0.0, min(1.0, 1.0 - (float(violation_cost or 0.0) / budget)))
