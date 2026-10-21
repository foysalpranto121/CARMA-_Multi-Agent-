"""
CARMA — Statistical analysis tests
Covers: McNemar, Friedman, post-hoc, Holm correction, bootstrap CI.
"""
import pytest

from apps.metrics.services.stats import (
    _holm_correction,
    bootstrap_ci,
    friedman_test,
    mcnemar_pairwise,
    mcnemar_test,
    posthoc_wilcoxon,
)


class TestMcNemar:
    def test_no_discordant_pairs(self):
        result = mcnemar_test([0, 1, 0, 1], [0, 1, 0, 1])
        assert result['p_value'] == 1.0
        assert result['significant'] is False

    def test_strong_difference_is_significant(self):
        a = [0] * 20
        b = [1] * 20
        result = mcnemar_test(a, b)
        assert result['p_value'] < 0.05
        assert result['significant'] is True
        assert result['only_b'] == 20
        assert result['only_a'] == 0
        assert result['odds_ratio'] == 0

    def test_no_data_returns_error(self):
        assert 'error' in mcnemar_test([], [])

    def test_pairwise_over_configurations(self):
        rows = []
        for index in range(20):
            rows.append({'benchmark_case_id': f'c{index}', 'config_code': 'B4',
                         'constraint_violated': 1})
            rows.append({'benchmark_case_id': f'c{index}', 'config_code': 'B7',
                         'constraint_violated': 0})
        results = mcnemar_pairwise(rows, 'constraint_violated')
        assert len(results) == 1
        assert results[0]['config_a'] == 'B4'
        assert results[0]['config_b'] == 'B7'
        assert results[0]['outcome']['p_corrected'] is not None


class TestHolm:
    def test_correction_is_monotonic_and_bounded(self):
        corrected = _holm_correction([0.01, 0.02, 0.04])
        assert all(0 <= p <= 1 for p in corrected)
        assert corrected == sorted(corrected)

    def test_empty_input(self):
        assert _holm_correction([]) == []


class TestFriedman:
    def test_requires_three_configurations(self):
        assert 'error' in friedman_test({'A': [1, 2, 3], 'B': [1, 2, 3]})

    def test_identical_samples_are_not_significant(self):
        samples = {'A': [1, 2, 3, 4], 'B': [1, 2, 3, 4], 'C': [1, 2, 3, 4]}
        result = friedman_test(samples)
        assert result['n_blocks'] == 4
        assert result['significant'] is False

    def test_different_samples_are_significant(self):
        samples = {'A': [1, 1, 1, 1], 'B': [5, 5, 5, 5], 'C': [9, 9, 9, 9]}
        result = friedman_test(samples)
        assert result['significant'] is True


class TestPosthoc:
    def test_wilcoxon_pairwise(self):
        samples = {'A': [1, 2, 3, 4], 'B': [5, 6, 7, 8], 'C': [9, 10, 11, 12]}
        results = posthoc_wilcoxon(samples)
        assert len(results) == 3
        for result in results:
            assert 'p_corrected' in result


class TestBootstrap:
    def test_interval_brackets_the_mean(self):
        values = [float(v) for v in range(1, 51)]
        result = bootstrap_ci(values, n_resamples=500)
        assert result['ci_lower'] <= result['mean'] <= result['ci_upper']

    def test_not_enough_data(self):
        assert 'error' in bootstrap_ci([1.0])
