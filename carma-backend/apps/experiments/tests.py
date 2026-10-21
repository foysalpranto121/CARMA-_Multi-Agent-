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
        from carma_engine.runners import get_runner

        runner = get_runner('B7', config=run_configuration, seed=42)
        output = runner.run(benchmark_case, run_configuration)
        assert output['error'] == ''
        assert 'plan' in output
        assert 'activity_seq' in output
        assert output['conformance_fitness'] is not None
        assert 0.0 <= output['conformance_fitness'] <= 1.0


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
                                                     experiment_run):
        from apps.audit.models import AuditLogEntry
        from apps.experiments.tasks import run_case

        outcome = run_case(str(experiment_run.id), str(benchmark_case.id))
        assert outcome['status'] != 'failed', outcome

        adaptation = Adaptation.objects.get(id=outcome['adaptation_id'])
        assert adaptation.run_id == experiment_run.id
        assert adaptation.status in ('success', 'violation', 'escalated', 'repair')

        entries = AuditLogEntry.objects.filter(adaptation_id=adaptation.id)
        assert entries.count() >= 3
        is_valid, broken_at = AuditLogEntry.verify_chain()
        assert is_valid is True, f'chain broken at {broken_at}'

    def test_aggregate_creates_run_result_and_metrics(self, benchmark_case,
                                                       experiment_run):
        from apps.experiments.tasks import aggregate_results, run_case

        run_case(str(experiment_run.id), str(benchmark_case.id))
        aggregate_results([], str(experiment_run.id))

        result = RunResult.objects.get(run=experiment_run)
        assert result.constraint_viol_rate is not None
        assert 0.0 <= result.constraint_viol_rate <= 1.0
        assert result.total_llm_tokens == 0

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
