"""
Base runner — the shared CARMA pipeline for one benchmark case.

    constraint graph → state estimation → retrieval → agent team
                     → symbolic verification (→ repair) → escalation gate
                     → execution → scoring against the reference

The runner is deterministic given ``(case, configuration)``: the only source
of randomness is the LLM.

A configuration switches on these components, and nothing else (the
factorial design of the study):

  * ``retrieval_type`` — none / vector / graph / constraint-aware (CAR)
  * ``multi_agent``    — the four-role team instead of a single agent
  * ``use_scv``        — the verifier *acts*: a rejected plan goes back to
                         the planner with the violation report, at most
                         ``k_repair_rounds`` times, and a plan that is still
                         rejected does not run
  * ``use_escalation`` — the confidence gate hands the case to a human (B7)

The verifier also *scores* every adaptation, whatever the configuration, so
that violation rates are comparable across configurations; scoring never
changes what runs.  Violations are counted on what was executed: a plan that
was blocked, declined or escalated put nothing into the process.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field

from ..constraint_knowledge.graph_builder import build_constraint_graph
from ..escalation.gate import TAU_DEFAULT, should_escalate
from ..llm.client import DEFAULT_MODEL, LLMUnavailable, build_llm
from ..retriever.constraint_aware import ConstraintAwareRetriever, plain_vector_rag
from ..scoring import score_adaptation
from ..state_estimator.replay import estimate_state
from ..verifier.symbolic import SCVVerifier

log = logging.getLogger('carma')

AGENT_ROLES = ('planner', 'critic', 'executor', 'policy_auditor')


@dataclass
class RunOutcome:
    """The result of running one case under one configuration."""
    plan: dict = field(default_factory=dict)
    plan_id: str = ''
    plan_source: str = ''
    # what the agent proposed, and what actually ran
    planned_seq: list = field(default_factory=list)
    activity_seq: list = field(default_factory=list)
    confidence: float | None = None
    exec_cost: float = 0.0
    viol_cost: float = 0.0
    hard_violation: bool = False
    unsafe_action: bool = False
    task_success: bool = False
    goal_reached: bool = False
    gold_exact_match: bool | None = None
    gold_similarity: float | None = None
    conformance_fitness: float = 0.0
    repair_rounds: int = 0
    status: str = 'failed'
    needs_escalation: bool = False
    escalation_reason: str = ''
    tokens_used: int = 0
    llm_calls: int = 0
    usd_cost: float | None = None
    served_by: dict = field(default_factory=dict)
    llm_backend: str = ''
    retrieved_docs: list = field(default_factory=list)
    retrieval_scores: dict = field(default_factory=dict)
    scv_approved: bool | None = None
    scv_token: str = ''
    violation_report: dict = field(default_factory=dict)
    error: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


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


def _usage_snapshot(llm) -> dict:
    """The cumulative usage counters of an LLM client (a runner reuses its client)."""
    usage = getattr(llm, 'usage', None)
    if usage is None:
        return {'tokens': 0, 'calls': 0, 'usd': 0.0, 'served_by': {}}
    return {
        'tokens': usage.total_tokens,
        'calls': usage.calls,
        'usd': float(getattr(usage, 'usd_cost', 0.0) or 0.0),
        'served_by': dict(getattr(usage, 'served_by', {}) or {}),
    }


class BaseRunner:
    """
    Shared implementation of one experiment configuration.

    :param code:           configuration code (``B0`` .. ``B7``)
    :param retrieval_type: ``none`` | ``vector`` | ``graph`` | ``constraint_aware``
    :param multi_agent:    use the 4-role agent team instead of a single agent
    :param use_scv:        the symbolic constraint verifier gates execution
    :param use_escalation: the confidence gate may hand the case to a human
    :param num_agents:     number of specialist agents
    :param uses_llm:       the configuration needs a model endpoint
    """

    code = 'B0'
    retrieval_type = 'none'
    multi_agent = False
    use_scv = False
    use_escalation = False
    num_agents = 1
    uses_llm = True

    def __init__(self, config=None, llm=None, seed=None):
        self.config = config
        self.seed = seed if seed is not None else getattr(config, 'seed', None)
        self._llm = llm

    # ── LLM ───────────────────────────────────────────────────
    def llm(self):
        if self._llm is None:
            model = getattr(self.config, 'llm_model', None) or DEFAULT_MODEL
            temperature = float(getattr(self.config, 'temperature', 0.0) or 0.0)
            max_tokens = int(getattr(self.config, 'max_tokens', 4096) or 4096)
            self._llm = build_llm(model=model, temperature=temperature,
                                  max_tokens=max_tokens, seed=self.seed)
        return self._llm

    def check_llm(self):
        """
        Fail fast when the configuration needs a model that cannot be reached.

        :raises LLMUnavailable: naming the missing setting
        """
        if not self.uses_llm:
            return
        require = getattr(self.llm(), '_require', None)
        if require is not None:
            require()

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

    def plan_case(self, benchmark_case, state, constraint_graph, evidence, feedback=None):
        """
        Produce the adaptation plan (overridden by the rule-based runner).

        :param feedback: the verifier's report on the previous plan, for an
                         SCV repair round
        """
        from ..agents.graph import build_agent_graph  # noqa: PLC0415

        llm = self.llm()
        graph = build_agent_graph(
            llm=llm,
            config=self.config,
            tau=self.tau(),
            agent_roles=self.agent_roles(),
            repair_rounds=self.repair_rounds(),
            multi_agent=self.multi_agent,
        )
        initial_state = {
            'perturbation': benchmark_case.perturbation or {},
            'prefix_trace': _executed_prefix(benchmark_case),
            'process_state': {**state.to_dict(),
                              'end_activities': _end_activities(benchmark_case.process)},
            'evidence': evidence,
            'constraint_graph_data': {},
            'plan': None,
            'violation_report': feedback,
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
        except LLMUnavailable:
            raise
        except Exception as exc:
            log.warning('Agent graph failed (%s) — no plan for this case.', exc)
            final_state = initial_state

        plan = final_state.get('plan') or {}
        extras = final_state.get('extras') or {}
        executor = extras.get('executor') or {}
        critic = extras.get('critic') or {}
        return {
            'plan': plan,
            'plan_id': plan.get('plan_id', ''),
            'plan_source': plan.get('plan_source', ''),
            'activity_seq': executor.get('activity_seq') or [],
            'confidence': critic.get('confidence', plan.get('confidence')),
            'exec_cost': executor.get('exec_cost', 0.0),
            'repair_rounds': int(final_state.get('repair_round', 0) or 0),
            'escalate': bool(final_state.get('escalate')),
            'escalation_reason': final_state.get('escalation_reason', ''),
            'llm_calls': int(final_state.get('llm_calls', 0) or 0),
            'agent_intents': final_state.get('agent_intents') or [],
        }

    def verify(self, benchmark_case, plan, constraint_graph, state, agent_intents=None):
        """
        Run the symbolic constraint verifier.

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
        before = _usage_snapshot(self._llm)

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
            planned = list(agent_result.get('activity_seq') or [])
            passed, token, viol_cost, report = None, '', 0.0, {}
            scv_repairs = 0
            if planned:
                passed, token, viol_cost, report = self.verify(
                    benchmark_case, agent_result.get('plan') or {}, constraint_graph, state,
                    agent_intents=agent_result.get('agent_intents'))
            if self.use_scv:
                # The action-side constraint layer: the verifier's report goes
                # back to the planner, at most k times.
                while planned and not passed and scv_repairs < self.repair_rounds():
                    scv_repairs += 1
                    agent_result = self.plan_case(benchmark_case, state, constraint_graph,
                                                  evidence, feedback=report)
                    planned = list(agent_result.get('activity_seq') or [])
                    if not planned:
                        passed, token, viol_cost, report = None, '', 0.0, {}
                        break
                    passed, token, viol_cost, report = self.verify(
                        benchmark_case, agent_result.get('plan') or {}, constraint_graph,
                        state, agent_intents=agent_result.get('agent_intents'))

            plan = agent_result.get('plan') or {}
            outcome.plan = plan
            outcome.plan_id = agent_result.get('plan_id', '')
            outcome.plan_source = agent_result.get('plan_source', '')
            outcome.planned_seq = planned
            outcome.confidence = agent_result.get('confidence')
            outcome.repair_rounds = int(agent_result.get('repair_rounds') or 0) + scv_repairs
            outcome.llm_calls = int(agent_result.get('llm_calls') or 0)
            outcome.scv_approved = passed
            outcome.violation_report = report

            escalate, reason = False, ''
            if self.use_escalation:
                escalate, reason = should_escalate(
                    plan,
                    verdict={'violation_report': report} if report else None,
                    constraint_graph=constraint_graph,
                    tau=self.tau(),
                    escalate_flag=agent_result.get('escalate', False),
                )
                reason = reason or agent_result.get('escalation_reason', '')
            outcome.needs_escalation = escalate
            outcome.escalation_reason = reason

            if escalate:
                outcome.status = 'escalated'
            elif not planned and outcome.plan_source in ('unparseable', 'error'):
                # The model produced no plan at all.  That is a failure, not
                # a decision to leave the case to a human.
                outcome.status = 'failed'
                outcome.error = f'The model returned no usable plan ({outcome.plan_source}).'
            elif not planned:
                outcome.status = 'declined'
            elif self.use_scv and not passed:
                outcome.status = 'blocked'
            else:
                # Least privilege: with the SCV on, the plan runs on its token.
                outcome.activity_seq = planned
                outcome.scv_token = token if self.use_scv else ''
                outcome.exec_cost = float(agent_result.get('exec_cost') or 0.0)
                outcome.viol_cost = float(viol_cost or 0.0)
                hard = [v for v in (report or {}).get('violations') or []
                        if v.get('severity', 'hard') == 'hard']
                outcome.hard_violation = bool(hard)
                outcome.unsafe_action = bool(hard) and any(
                    activity.get('is_write') for activity in plan.get('activities') or [])
                if outcome.viol_cost > 0:
                    outcome.status = 'violation'
                elif outcome.repair_rounds:
                    outcome.status = 'repair'
                else:
                    outcome.status = 'success'

            outcome.conformance_fitness = _conformance_fitness(
                outcome.viol_cost, constraint_graph)
            score = score_adaptation(
                benchmark_case.gold_adaptation, benchmark_case.gold_activity_seq,
                outcome.activity_seq, outcome.status, outcome.hard_violation,
                end_activities=_end_activities(benchmark_case.process))
            outcome.goal_reached = score.goal_reached
            outcome.task_success = score.task_success
            outcome.gold_exact_match = score.exact_match
            outcome.gold_similarity = score.similarity

        except LLMUnavailable as exc:
            outcome.status = 'failed'
            outcome.error = str(exc)
            log.warning('LLM unavailable for case %s: %s', getattr(benchmark_case, 'id', '?'), exc)
        except Exception as exc:
            outcome.status = 'failed'
            outcome.error = str(exc)
            log.exception('Runner %s failed: %s', self.code, exc)

        self._record_usage(outcome, before)
        outcome_dict = outcome.to_dict()
        outcome_dict['latency_s'] = time.monotonic() - started
        return outcome_dict

    def _record_usage(self, outcome: RunOutcome, before: dict):
        """Attribute the LLM usage of this case (the delta since it started)."""
        llm = self._llm
        if llm is None:
            outcome.llm_backend = 'rule_based' if not self.uses_llm else ''
            outcome.usd_cost = 0.0 if not self.uses_llm else None
            return
        after = _usage_snapshot(llm)
        outcome.tokens_used = after['tokens'] - before['tokens']
        outcome.llm_calls = max(outcome.llm_calls, after['calls'] - before['calls'])
        outcome.served_by = {
            model: count - before['served_by'].get(model, 0)
            for model, count in after['served_by'].items()
            if count - before['served_by'].get(model, 0) > 0
        }
        outcome.llm_backend = getattr(llm, 'provider', '') or ''
        if outcome.llm_backend in ('anthropic', 'groq', 'mock'):
            outcome.usd_cost = round(after['usd'] - before['usd'], 6)


# ── helpers ───────────────────────────────────────────────────
def _end_activities(process) -> list[str]:
    """
    The activities the process's training cases end with.

    ``import_benchmark`` records them in ``Process.metadata``; for a process
    imported before that, they are computed once from the training split and
    stored.
    """
    metadata = dict(getattr(process, 'metadata', None) or {})
    if 'end_activities' in metadata:
        return list(metadata['end_activities'] or [])
    dataset = metadata.get('dataset')
    if not dataset:
        return []
    from apps.benchmark.models import Case  # noqa: PLC0415
    from apps.benchmark.services.process_discovery import end_activities  # noqa: PLC0415

    traces = (Case.objects.filter(event_log__name=dataset, attributes__split='train')
              .values_list('prefix_trace', flat=True).iterator())
    ends = end_activities([event.get('activity') for event in (trace or [])] for trace in traces)
    metadata['end_activities'] = ends
    type(process).objects.filter(pk=process.pk).update(metadata=metadata)
    process.metadata = metadata
    return ends


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
