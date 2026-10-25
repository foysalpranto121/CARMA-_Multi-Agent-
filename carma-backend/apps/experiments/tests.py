"""
CARMA — Engine + experiment pipeline tests

Covers the Day-2 gate of the sprint plan: a benchmark case runs end-to-end
through a runner, an adaptation is produced, the audit chain is written and
the metrics are aggregated.
"""
import pytest

from apps.benchmark.models import BenchmarkCase, BenchmarkScenario, Case, EventLog
from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration, RunResult
from apps.processes.models import Constraint, ConstraintSet, CorpusDocument, Process

PREFIX = [
    {'activity': 'submit_request', 'timestamp': '2024-01-01T10:00:00'},
    {'activity': 'check_income',   'timestamp': '2024-01-01T10:05:00'},
]


@pytest.fixture
def process(db):
    return Process.objects.create(
        name='Loan Application',
        model_type='bpmn',
        model_xml='',
        activities=['submit_request', 'check_income', 'approve_loan', 'reject_loan'],
    )


@pytest.fixture
def constraint_set(process):
    constraint_set = ConstraintSet.objects.create(process=process, name='baseline')
    Constraint.objects.create(
        constraint_set=constraint_set,
        constraint_type='response',
        activity_a='check_income',
        activity_b='approve_loan',
        parameters={'activities': ['check_income', 'approve_loan']},
        violation_cost=2.0,
    )
    Constraint.objects.create(
        constraint_set=constraint_set,
        constraint_type='precedence',
        activity_a='check_income',
        activity_b='approve_loan',
        parameters={'activities': ['check_income', 'approve_loan']},
        violation_cost=2.0,
    )
    return constraint_set


@pytest.fixture
def corpus(process):
    return CorpusDocument.objects.create(
        process=process,
        title='Income verification SOP',
        doc_type='sop',
        content='Verify the applicant income before approving the loan.',
        stage='check_income',
        metadata={'activity_tags': ['check_income', 'approve_loan']},
    )


@pytest.fixture
def benchmark_case(process, constraint_set):
    event_log = EventLog.objects.create(name='bpi2017', display_name='BPI 2017')
    case = Case.objects.create(
        event_log=event_log, case_id='case-1', prefix_trace=PREFIX)
    scenario = BenchmarkScenario.objects.create(
        code='S0', name='Nominal', description='No perturbation',
        perturbation_template={'type': 'nominal'})
    return BenchmarkCase.objects.create(
        case=case, scenario=scenario, process=process, constraint_set=constraint_set,
        perturbation={'type': 'nominal', 'description': 'No perturbation'},
        gold_adaptation={'activities': []},
        is_validated=True,
    )


@pytest.fixture
def run_configuration(db):
    return RunConfiguration.objects.create(
        code='B7', name='CARMA (Full)', use_car=True, use_scv=True,
        multi_agent=True, num_agents=4, llm_model='gpt-4o', temperature=0.0,
    )


@pytest.fixture
def experiment_run(run_configuration, process, constraint_set):
    return ExperimentRun.objects.create(
        configuration=run_configuration, process=process,
        constraint_set=constraint_set, seed=42, status='pending')


@pytest.fixture
def mock_llm(monkeypatch):
    """Runners built by the pipeline get the deterministic test double."""
    from carma_engine.llm.mock import MockLLM

    monkeypatch.setattr('carma_engine.runners.base.build_llm', lambda **kwargs: MockLLM())


@pytest.fixture
def no_credentials(monkeypatch):
    """No model credential, whatever carma-backend/.env holds."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', '')
    monkeypatch.setenv('OPENAI_API_KEY', '')


class ScriptedLLM:
    """A test double that always proposes the same plan and approves it."""

    provider = 'mock'
    model = 'scripted'

    def __init__(self, activities):
        from carma_engine.llm.client import Usage

        self.activities = activities
        self.usage = Usage()

    def available(self):
        return True

    def invoke_json(self, system_prompt, human_prompt, default=None):
        self.usage.calls += 1
        if 'critic' in system_prompt.lower():
            return {'approved': True, 'goal_reachable': True, 'confidence': 0.9, 'issues': []}
        if 'planner' in system_prompt.lower():
            if self.activities is None:
                return {}
            return {
                'plan_id': 'scripted-plan',
                'activities': [{'activity_name': name, 'role': 'officer',
                                'data_payload': {}, 'is_write': False}
                               for name in self.activities],
                'evidence_ids': [], 'confidence': 0.9,
                'rationale': 'scripted', 'goal_reachable': bool(self.activities),
            }
        return {'summary': 'framing', 'intents': [], 'conflicts': []}


class TestRunners:
    def test_matrix_covers_b0_to_b7(self):
        from carma_engine.runners import RUNNER_MATRIX

        assert sorted(RUNNER_MATRIX) == [f'B{i}' for i in range(8)]

    def test_unknown_code_raises(self):
        from carma_engine.runners import get_runner

        with pytest.raises(KeyError):
            get_runner('B99')

    def test_b0_rule_based_runs_without_llm(self, benchmark_case, run_configuration):
        from carma_engine.runners import get_runner

        run_configuration.code = 'B0'
        run_configuration.save()
        runner = get_runner('B0', config=run_configuration, seed=42)
        output = runner.run(benchmark_case, run_configuration)
        assert output['status'] in ('success', 'violation', 'escalated', 'repair')
        assert output['plan']['activities'] is not None
        assert output['llm_calls'] == 0

    def test_b7_runs_end_to_end(self, benchmark_case, run_configuration, corpus):
        from carma_engine.llm.mock import MockLLM
        from carma_engine.runners import get_runner

        runner = get_runner('B7', config=run_configuration, seed=42, llm=MockLLM())
        output = runner.run(benchmark_case, run_configuration)
        assert output['error'] == ''
        assert 'plan' in output
        assert 'activity_seq' in output
        assert output['llm_backend'] == 'mock'
        assert output['conformance_fitness'] is not None
        assert 0.0 <= output['conformance_fitness'] <= 1.0

    def test_llm_configuration_without_credentials_fails_loudly(
            self, benchmark_case, run_configuration, no_credentials):
        """No key must never turn into a rule-based plan recorded under B7."""
        from carma_engine.runners import get_runner

        output = get_runner('B7', config=run_configuration, seed=42).run(
            benchmark_case, run_configuration)
        assert output['status'] == 'failed'
        assert 'OPENAI_API_KEY' in output['error']
        assert output['activity_seq'] == []
        assert output['task_success'] is False


class TestStateEstimator:
    def test_fallback_estimator_runs(self, benchmark_case, constraint_set):
        from carma_engine.constraint_knowledge.graph_builder import build_constraint_graph
        from carma_engine.state_estimator import estimate_state

        graph = build_constraint_graph(benchmark_case.process,
                                       constraint_sets=[constraint_set])
        state = estimate_state(PREFIX, benchmark_case.process, constraint_graph=graph)
        assert state.stage == 'check_income'
        assert 'approve_loan' in state.enabled_activities


class TestVerifier:
    def test_token_round_trip(self):
        from carma_engine.verifier.symbolic import SCVVerifier, verify_token

        verifier = SCVVerifier()
        token = verifier.issue_token({'plan_id': 'p1'})
        assert verify_token(token) is True
        assert verify_token(token + 'x') is False
        assert verify_token('') is False

    def test_violation_is_detected(self, benchmark_case, constraint_set):
        from carma_engine.constraint_knowledge.graph_builder import build_constraint_graph
        from carma_engine.verifier.symbolic import SCVVerifier

        graph = build_constraint_graph(benchmark_case.process,
                                       constraint_sets=[constraint_set])
        plan = {'plan_id': 'p1', 'activities': [
            {'activity_name': 'approve_loan', 'role': 'officer', 'data_payload': {}},
        ]}
        passed, token, cost, report = SCVVerifier().verify(
            plan=plan, prefix_trace=[], process=benchmark_case.process,
            constraint_graph=graph)
        # "response(check_income -> approve_loan)" is satisfied only when
        # check_income precedes approve_loan; an empty prefix violates it.
        assert passed is False
        assert token is None
        assert cost > 0
        assert report['violations']

    def test_conflicting_intents_are_detected(self):
        from carma_engine.verifier.conflict_detector import detect_conflicts

        violations = detect_conflicts([
            {'agent': 'planner', 'intent': 'approve the loan'},
            {'agent': 'auditor', 'intent': 'reject the loan'},
        ])
        assert len(violations) == 1
        assert violations[0]['constraint_type'] == 'conflict'


class TestExperimentPipeline:
    def test_run_case_persists_adaptation_and_audit(self, benchmark_case,
                                                     experiment_run, mock_llm):
        from apps.audit.models import AuditLogEntry
        from apps.experiments.tasks import run_case

        outcome = run_case(str(experiment_run.id), str(benchmark_case.id))
        assert outcome['status'] != 'failed', outcome

        adaptation = Adaptation.objects.get(id=outcome['adaptation_id'])
        assert adaptation.run_id == experiment_run.id
        assert adaptation.status in ('success', 'violation', 'escalated', 'repair',
                                     'blocked', 'declined')
        assert adaptation.llm_backend == 'mock'

        entries = AuditLogEntry.objects.filter(adaptation_id=adaptation.id)
        assert entries.count() >= 3
        is_valid, broken_at = AuditLogEntry.verify_chain()
        assert is_valid is True, f'chain broken at {broken_at}'

    def test_aggregate_creates_run_result_and_metrics(self, benchmark_case,
                                                       experiment_run, mock_llm):
        from apps.experiments.tasks import aggregate_results, run_case

        run_case(str(experiment_run.id), str(benchmark_case.id))
        aggregate_results([], str(experiment_run.id))

        result = RunResult.objects.get(run=experiment_run)
        assert result.constraint_viol_rate is not None
        assert 0.0 <= result.constraint_viol_rate <= 1.0
        assert result.total_llm_tokens > 0

        from apps.metrics.models import RunMetrics
        assert RunMetrics.objects.filter(run=experiment_run).exists()


class TestSeedCommand:
    def test_seeds_all_eight_configurations(self, db):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('seed_configurations', stdout=out)
        assert RunConfiguration.objects.count() == 8
        codes = set(RunConfiguration.objects.values_list('code', flat=True))
        assert codes == {f'B{i}' for i in range(8)}

        b7 = RunConfiguration.objects.get(code='B7')
        assert b7.use_car is True
        assert b7.use_scv is True
        assert b7.multi_agent is True
        assert b7.num_agents == 4

        b0 = RunConfiguration.objects.get(code='B0')
        assert b0.use_car is False
        assert b0.use_scv is False
        assert b0.multi_agent is False

        # B6 is the action-side cell of the 2x2: vector retrieval plus the SCV.
        b6 = RunConfiguration.objects.get(code='B6')
        assert b6.use_car is False
        assert b6.use_scv is True
        assert 'VectorRAG' in b6.name
        assert b7.llm_model == 'claude-opus-5-5'

        # idempotent
        call_command('seed_configurations', stdout=StringIO())
        assert RunConfiguration.objects.count() == 8


class TestExperimentViews:
    def test_matrix_endpoint_lists_b0_to_b7(self, db, client, admin_user):
        from rest_framework.test import APIClient

        api = APIClient()
        api.force_authenticate(user=admin_user)
        response = api.get('/api/v1/experiments/matrix/')
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 8
        assert {row['code'] for row in rows} == {f'B{i}' for i in range(8)}
        b7 = next(row for row in rows if row['code'] == 'B7')
        assert b7['use_scv'] is True
        assert b7['retrieval'] == 'constraint_aware'

    def test_export_returns_csv(self, db, client, admin_user, experiment_run):
        from rest_framework.test import APIClient

        api = APIClient()
        api.force_authenticate(user=admin_user)
        response = api.get(f'/api/v1/experiments/{experiment_run.id}/export/')
        assert response.status_code == 200
        assert 'text/csv' in response['Content-Type']
        body = response.content.decode()
        assert 'config_code' in body
        assert 'conformance_fitness' in body


class TestSystemStatus:
    def test_reports_real_component_state(self, db, admin_user):
        from rest_framework.test import APIClient

        api = APIClient()
        api.force_authenticate(user=admin_user)
        response = api.get('/api/v1/system/status/')
        assert response.status_code == 200
        payload = response.json()
        assert payload['database'] == 'ok'
        assert payload['status'] == 'ok'
        assert payload['engine']['configurations'] == [f'B{i}' for i in range(8)]
        # The counts must reflect the database, not hardcoded numbers.
        assert payload['counts']['configurations'] == 0
        assert payload['counts']['runs'] == 0
        assert 'llm' in payload
        assert 'vector_store' in payload
        assert 'task_broker' in payload

    def test_requires_authentication(self, db):
        from rest_framework.test import APIClient

        response = APIClient().get('/api/v1/system/status/')
        assert response.status_code in (401, 403)


class TestScoring:
    """Task success and adaptation correctness against the gold (Section VI-C)."""

    def test_reached_goal_with_exact_sequence(self):
        from carma_engine.scoring import score_adaptation

        score = score_adaptation({'strategy': 'follow_observed_path'},
                                 ['a', 'b'], ['a', 'b'], 'success', False)
        assert score.task_success is True
        assert score.exact_match is True
        assert score.similarity == 1.0

    def test_partial_match(self):
        from carma_engine.scoring import score_adaptation

        score = score_adaptation({'strategy': 'follow_observed_path'},
                                 ['a', 'b', 'c'], ['a', 'c'], 'success', False)
        assert score.goal_reached is True
        assert score.exact_match is False
        assert score.partial_match is True
        assert score.similarity == 0.8

    def test_hard_violation_is_not_a_success(self):
        from carma_engine.scoring import score_adaptation

        score = score_adaptation({'strategy': 'follow_observed_path'},
                                 ['a'], ['a'], 'violation', True)
        assert score.goal_reached is True
        assert score.task_success is False

    def test_a_non_empty_plan_is_not_automatically_a_success(self):
        from carma_engine.scoring import score_adaptation

        score = score_adaptation({'strategy': 'follow_observed_path'},
                                 ['approve'], ['reject'], 'success', False)
        assert score.task_success is False

    def test_human_strategies_need_the_case_left_to_a_human(self):
        from carma_engine.scoring import score_adaptation

        gold = {'strategy': 'request_clarification'}
        assert score_adaptation(gold, [], [], 'escalated', False).task_success is True
        assert score_adaptation(gold, [], [], 'declined', False).task_success is True
        assert score_adaptation(gold, [], [], 'blocked', False).task_success is False
        assert score_adaptation(gold, [], [], 'failed', False).task_success is False
        assert score_adaptation(gold, [], ['a'], 'success', False).task_success is False


class TestPlannerIntegrity:
    """A model's answer is never replaced by a heuristic plan."""

    @staticmethod
    def _plan(llm):
        from carma_engine.agents.planner import planner_node

        state = {'process_state': {'enabled_activities': ['approve_loan']},
                 'evidence': [], 'prefix_trace': PREFIX, 'perturbation': {}}
        return planner_node(llm)(state)['plan']

    def test_a_decline_is_kept(self):
        plan = self._plan(ScriptedLLM([]))
        assert plan['plan_source'] == 'llm'
        assert plan['activities'] == []

    def test_unparseable_output_is_not_replaced_by_a_heuristic(self):
        plan = self._plan(ScriptedLLM(None))
        assert plan['plan_source'] == 'unparseable'
        assert plan['activities'] == []

    def test_an_unreachable_model_propagates(self, no_credentials):
        from carma_engine.llm.client import LLMClient, LLMUnavailable

        with pytest.raises(LLMUnavailable):
            self._plan(LLMClient(model='claude-opus-5-5'))


class TestFactorialGating:
    """B4, B6 and B7 differ only in what the verifier and the gate may do."""

    @pytest.fixture
    def scored_case(self, benchmark_case):
        benchmark_case.gold_adaptation = {'strategy': 'follow_observed_path'}
        benchmark_case.gold_activity_seq = ['approve_loan']
        benchmark_case.save()
        return benchmark_case

    @staticmethod
    def _run(code, case, activities):
        from carma_engine.runners import get_runner

        config = RunConfiguration.objects.create(
            code=code, name=code, llm_model='claude-opus-5-5', k_repair_rounds=2)
        return get_runner(code, config=config, seed=42,
                          llm=ScriptedLLM(activities)).run(case, config)

    def test_without_the_scv_a_violating_plan_runs(self, scored_case):
        output = self._run('B4', scored_case, ['reject_loan'])
        assert output['status'] == 'violation'
        assert output['activity_seq'] == ['reject_loan']
        assert output['hard_violation'] is True
        assert output['task_success'] is False
        assert output['needs_escalation'] is False

    def test_the_scv_repairs_then_blocks_a_violating_plan(self, scored_case):
        output = self._run('B6', scored_case, ['reject_loan'])
        assert output['status'] == 'blocked'
        assert output['planned_seq'] == ['reject_loan']
        assert output['activity_seq'] == []
        assert output['hard_violation'] is False
        assert output['repair_rounds'] == 2
        assert output['needs_escalation'] is False

    def test_carma_escalates_a_violating_plan(self, scored_case):
        output = self._run('B7', scored_case, ['reject_loan'])
        assert output['status'] == 'escalated'
        assert output['activity_seq'] == []
        assert output['needs_escalation'] is True

    def test_a_compliant_plan_succeeds_against_the_gold(self, scored_case):
        for code in ('B4', 'B6', 'B7'):
            output = self._run(code, scored_case, ['approve_loan'])
            assert output['status'] == 'success', (code, output['escalation_reason'])
            assert output['task_success'] is True
            assert output['gold_exact_match'] is True

    def test_single_agent_makes_one_call(self, scored_case):
        output = self._run('B1', scored_case, ['approve_loan'])
        assert output['llm_calls'] == 1


class TestClaudeClient:
    @staticmethod
    def _client(monkeypatch, captured, model='claude-opus-5-5', stop_reason='end_turn',
                served=None, iterations=None):
        from types import SimpleNamespace

        from carma_engine.llm.client import LLMClient

        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test-key')
        monkeypatch.setenv('ANTHROPIC_EFFORT', 'medium')
        client = LLMClient(model=model, temperature=0.2, seed=7)

        def create(**params):
            captured.update(params)
            return SimpleNamespace(
                stop_reason=stop_reason, stop_details=None, model=served or model,
                content=[SimpleNamespace(type='thinking', thinking=''),
                         SimpleNamespace(type='text', text='{"ok": true}')],
                usage=SimpleNamespace(input_tokens=1000, output_tokens=500,
                                      iterations=iterations))

        client._anthropic = SimpleNamespace(
            beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        return client

    def test_request_sends_no_sampling_parameters(self, monkeypatch):
        captured = {}
        client = self._client(monkeypatch, captured)
        assert client.invoke_json('system', 'human') == {'ok': True}
        assert captured['model'] == 'claude-opus-5-5'
        assert captured['system'] == 'system'
        assert 'temperature' not in captured
        assert 'seed' not in captured
        assert captured['max_tokens'] >= 16000
        assert captured['output_config'] == {'effort': 'medium'}
        assert captured['fallbacks'] == 'default'
        assert captured['betas'] == ['server-side-fallback-2026-07-01']

    def test_usage_records_cost_and_the_serving_model(self, monkeypatch):
        from types import SimpleNamespace

        captured = {}
        client = self._client(
            monkeypatch, captured, served='claude-opus-5',
            iterations=[SimpleNamespace(type='message'),
                        SimpleNamespace(type='fallback_message')])
        client.invoke('s', 'h')
        assert client.usage.calls == 1
        assert client.usage.served_by == {'claude-opus-5': 1}
        assert client.usage.fallbacks == 1
        assert client.usage.usd_cost == pytest.approx((1000 * 5 + 500 * 25) / 1e6)

    def test_haiku_sends_no_fallback(self, monkeypatch):
        captured = {}
        self._client(monkeypatch, captured, model='claude-haiku-5-5').invoke('s', 'h')
        assert 'fallbacks' not in captured
        assert 'betas' not in captured

    def test_a_refusal_returns_no_text(self, monkeypatch):
        captured = {}
        client = self._client(monkeypatch, captured, stop_reason='refusal')
        assert client.invoke('s', 'h') == ''
        assert client.usage.refusals == 1

    def test_the_key_comes_from_the_environment_or_env_file(self, monkeypatch, no_credentials):
        from carma_engine.llm.client import LLMClient

        assert LLMClient(model='claude-opus-5-5').available() is False
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-real-key')
        assert LLMClient(model='claude-opus-5-5').available() is True

    def test_ollama_receives_its_own_model_tag(self, monkeypatch):
        import io
        import json

        from carma_engine.llm.client import LLMClient

        sent = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen(request, timeout=None):
            sent.update(json.loads(request.data))
            return Response(json.dumps({'message': {'content': 'hi'}}).encode())

        monkeypatch.setattr('urllib.request.urlopen', urlopen)
        assert LLMClient(model='qwen2.5-32b').invoke('s', 'h') == 'hi'
        assert sent['model'] == 'qwen2.5:32b'


class TestOpenAIClient:
    def test_sends_the_protocol_sampling_and_records_the_snapshot(self, monkeypatch):
        import io
        import json

        from carma_engine.llm.client import LLMClient

        monkeypatch.setenv('OPENAI_API_KEY', 'sk-proj-test-key')
        sent = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen(request, timeout=None):
            sent.update(json.loads(request.data))
            return Response(json.dumps({
                'model': 'gpt-4o-2024-08-06',
                'choices': [{'message': {'content': '{"ok": true}'}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 3},
            }).encode())

        monkeypatch.setattr('urllib.request.urlopen', urlopen)
        client = LLMClient(model='gpt-4o', temperature=0.2, seed=42)
        assert client.invoke_json('s', 'h') == {'ok': True}
        assert sent['temperature'] == 0.2
        assert sent['seed'] == 42
        assert client.usage.served_by == {'gpt-4o-2024-08-06': 1}
        assert client.usage.total_tokens == 13


class TestRunExperimentCommand:
    def test_stops_before_the_first_case_without_credentials(self, benchmark_case,
                                                             no_credentials):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        call_command('seed_configurations', stdout=StringIO())
        with pytest.raises(CommandError, match='ANTHROPIC_API_KEY'):
            call_command('run_experiment', '--configs', 'B7',
                         stdout=StringIO(), stderr=StringIO())
        assert not Adaptation.objects.exists()

    def test_records_the_audit_chain_like_the_celery_path(self, benchmark_case):
        from io import StringIO

        from django.core.management import call_command

        from apps.audit.models import AuditLogEntry

        call_command('seed_configurations', stdout=StringIO())
        call_command('run_experiment', '--configs', 'B7', '--mock-llm',
                     stdout=StringIO(), stderr=StringIO())
        adaptation = Adaptation.objects.get()
        assert adaptation.llm_backend == 'mock'
        assert AuditLogEntry.objects.filter(adaptation_id=adaptation.id).count() >= 3
