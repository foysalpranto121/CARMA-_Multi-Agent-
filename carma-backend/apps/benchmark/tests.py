"""
CARMA — Gold annotation and inter-annotator agreement tests
"""
import pytest
from rest_framework.test import APIClient

from apps.benchmark.models import BenchmarkCase, BenchmarkScenario, Case, EventLog, GoldAnnotation
from apps.metrics.services.stats import cohen_kappa
from apps.processes.models import Process
from apps.users.models import User


class TestCohenKappa:
    def test_perfect_agreement(self):
        result = cohen_kappa(['a', 'b', 'a', 'c'], ['a', 'b', 'a', 'c'])
        assert result['kappa'] == pytest.approx(1.0)
        assert result['observed_agreement'] == 1.0

    def test_known_value(self):
        # 2x2 table [[20, 5], [10, 15]]: p_o = 0.7, p_e = 0.5, kappa = 0.4
        a = ['yes'] * 25 + ['no'] * 25
        b = ['yes'] * 20 + ['no'] * 5 + ['yes'] * 10 + ['no'] * 15
        result = cohen_kappa(a, b)
        assert result['observed_agreement'] == pytest.approx(0.7)
        assert result['expected_agreement'] == pytest.approx(0.5)
        assert result['kappa'] == pytest.approx(0.4)

    def test_undefined_when_both_use_one_label(self):
        assert cohen_kappa(['a', 'a'], ['a', 'a'])['kappa'] is None

    def test_no_items(self):
        assert 'error' in cohen_kappa([], [])


class TestReferenceValidation:
    """A reference that breaks the frame is only kept where that is the right answer."""

    @staticmethod
    def _report(strategy, cost):
        from types import SimpleNamespace

        from apps.benchmark.services.scenario_builder import validate_case

        trace = [{'activity': 'a'}, {'activity': 'b'}, {'activity': 'c'}]
        benchmark_case = SimpleNamespace(
            case=SimpleNamespace(prefix_trace=trace), prefix_trace=trace[:1],
            gold_activity_seq=['b', 'c'], perturbation={}, perturbation_text='nominal',
            gold_adaptation={'strategy': strategy}, gold_viol_cost=cost)
        return validate_case(benchmark_case, SimpleNamespace(activities=['a', 'b', 'c']))

    def test_a_violating_observed_path_is_not_validated(self):
        assert self._report('follow_observed_path', 2.0)['validated'] is False

    def test_a_minimum_cost_exception_path_stays(self):
        assert self._report('take_observed_alternative_path', 2.0)['validated'] is True

    def test_a_compliant_reference_passes(self):
        assert self._report('follow_observed_path', 0.0)['validated'] is True


def _annotator(name):
    return User.objects.create_user(
        email=f'{name}@carma.test', password='Carma-Test-2026!',
        first_name=name.title(), last_name='Annotator', username=name, role='annotator')


@pytest.fixture
def benchmark_cases(db):
    process = Process.objects.create(name='Loan', model_type='bpmn', model_xml='',
                                     activities=['a', 'b'])
    event_log = EventLog.objects.create(name='bpi2017', display_name='BPI 2017')
    scenario = BenchmarkScenario.objects.create(code='S4', name='Ambiguous',
                                                perturbation_template={})
    cases = []
    for index in range(3):
        case = Case.objects.create(event_log=event_log, case_id=f'c{index}', prefix_trace=[])
        cases.append(BenchmarkCase.objects.create(
            case=case, scenario=scenario, process=process, perturbation={},
            gold_adaptation={'strategy': 'request_clarification'}, is_validated=True))
    return cases


class TestAnnotationApi:
    @staticmethod
    def _post(user, benchmark_case, strategy):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.post(f'/api/v1/benchmark/cases/{benchmark_case.id}/annotations/',
                           {'strategy': strategy, 'activity_seq': [], 'notes': ''},
                           format='json')

    def test_two_annotators_and_their_agreement(self, benchmark_cases, admin_user):
        first, second = _annotator('ann1'), _annotator('ann2')
        for benchmark_case in benchmark_cases:
            assert self._post(first, benchmark_case, 'request_clarification').status_code == 201
        self._post(second, benchmark_cases[0], 'request_clarification')
        self._post(second, benchmark_cases[1], 'request_clarification')
        self._post(second, benchmark_cases[2], 'escalate_conflict')

        benchmark_cases[0].refresh_from_db()
        assert benchmark_cases[0].annotator_1 == first
        assert benchmark_cases[0].annotator_2 == second

        client = APIClient()
        client.force_authenticate(user=admin_user)
        body = client.get('/api/v1/benchmark/cases/agreement/').json()
        assert body['double_annotated'] == 3
        assert body['observed_agreement'] == pytest.approx(2 / 3)
        assert body['disagreements'] == [str(benchmark_cases[2].id)]

    def test_revising_an_annotation_does_not_duplicate_it(self, benchmark_cases):
        annotator = _annotator('ann1')
        self._post(annotator, benchmark_cases[0], 'request_clarification')
        self._post(annotator, benchmark_cases[0], 'escalate_conflict')
        annotations = GoldAnnotation.objects.filter(benchmark_case=benchmark_cases[0])
        assert annotations.count() == 1
        assert annotations.get().strategy == 'escalate_conflict'

    def test_only_annotators_may_annotate(self, benchmark_cases, researcher_user):
        response = self._post(researcher_user, benchmark_cases[0], 'request_clarification')
        assert response.status_code == 403

    def test_unknown_strategy_is_rejected(self, benchmark_cases):
        response = self._post(_annotator('ann1'), benchmark_cases[0], 'guess')
        assert response.status_code == 400
