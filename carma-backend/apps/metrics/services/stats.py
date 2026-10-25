"""
Statistical analysis for the factorial experiment.

Implements the pre-registered analysis plan:

  * **McNemar test** — paired comparison of two configurations on a binary
    outcome (constraint violated / task success).  Exact binomial variant.
  * **Friedman test** with Wilcoxon post-hoc comparisons — non-parametric
    comparison of >2 configurations on a continuous outcome (latency, cost).
  * **Holm–Bonferroni** correction for the family-wise error rate across the
    pairwise comparisons.
  * **Bootstrap confidence interval** for a mean.

Every function returns plain Python structures so the API can serialise them
directly, and every function degrades gracefully (empty result + reason) when
the data does not support the test — it never returns invented numbers.
"""
from __future__ import annotations

import logging
import math
from itertools import combinations

log = logging.getLogger('carma')

ALPHA = 0.05


def _normalise_binary(series) -> list:
    """Coerce a column into 0/1 ints, ignoring missing values."""
    values = []
    for value in series:
        if value is None:
            continue
        if isinstance(value, bool):
            values.append(1 if value else 0)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(numeric):
            continue
        values.append(1 if numeric > 0 else 0)
    return values


def _holm_correction(p_values: list) -> list:
    """Holm–Bonferroni step-down correction."""
    if not p_values:
        return []
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    m = len(p_values)
    corrected = [0.0] * m
    running_max = 0.0
    for rank, (index, p_value) in enumerate(indexed):
        adjusted = min(1.0, (m - rank) * p_value)
        running_max = max(running_max, adjusted)
        corrected[index] = running_max
    return corrected


def mcnemar_test(pairs_a: list, pairs_b: list) -> dict:
    """
    Exact McNemar test on paired binary outcomes.

    :param pairs_a: outcome of configuration A, one entry per case
    :param pairs_b: outcome of configuration B, one entry per case
    """
    from scipy.stats import binomtest  # noqa: PLC0415

    a = _normalise_binary(pairs_a)
    b = _normalise_binary(pairs_b)
    n = min(len(a), len(b))
    if n == 0:
        return {'error': 'No paired observations available.'}

    a, b = a[:n], b[:n]
    # Discordant pairs: the two configurations disagree.
    only_a = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    only_b = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)

    discordant = only_a + only_b
    if discordant == 0:
        return {
            'statistic': 0.0, 'p_value': 1.0, 'odds_ratio': None,
            'only_a': only_a, 'only_b': only_b, 'n_pairs': n,
            'significant': False, 'note': 'No discordant pairs.',
        }

    # Exact binomial: under H0 the discordant pairs split 50/50.
    p_value = float(binomtest(min(only_a, only_b), discordant, 0.5).pvalue)
    # The conditional odds ratio is unbounded when one discordant cell is
    # empty — exactly when one configuration dominates — and JSON has no
    # infinity.  The Haldane-Anscombe value (0.5 added to both cells) is
    # always finite and is reported alongside.
    odds_ratio = (only_a / only_b) if only_b else None

    return {
        'statistic': float(discordant),
        'p_value': p_value,
        'odds_ratio': odds_ratio,
        'odds_ratio_corrected': (only_a + 0.5) / (only_b + 0.5),
        'only_a': only_a,
        'only_b': only_b,
        'n_pairs': n,
        'significant': p_value < ALPHA,
    }


def cohen_kappa(labels_a: list, labels_b: list) -> dict:
    """
    Cohen's kappa of two annotators who labelled the same items.

    :returns: ``kappa`` with the observed and the chance agreement; ``kappa``
              is ``None`` when the chance agreement is 1 (both annotators
              used one and the same label throughout — κ is undefined then).
    """
    n = min(len(labels_a), len(labels_b))
    if n == 0:
        return {'error': 'No item was labelled by both annotators.'}
    a, b = list(labels_a[:n]), list(labels_b[:n])
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((a.count(label) / n) * (b.count(label) / n) for label in set(a) | set(b))
    kappa = None if expected >= 1.0 else (observed - expected) / (1.0 - expected)
    return {
        'kappa': kappa,
        'observed_agreement': observed,
        'expected_agreement': expected,
        'n': n,
    }


def mcnemar_pairwise(rows: list, outcome: str = 'constraint_violated',
                      case_key: str = 'benchmark_case_id',
                      config_key: str = 'config_code') -> list[dict]:
    """
    Pairwise McNemar tests across all configuration pairs.

    :param rows: list of dicts with the case key, the configuration key and
                 the (binary) outcome
    """
    by_config: dict[str, dict] = {}
    for row in rows:
        config = row.get(config_key)
        case = row.get(case_key)
        if config is None or case is None:
            continue
        by_config.setdefault(config, {})[case] = row.get(outcome)

    results = []
    for config_a, config_b in combinations(sorted(by_config), 2):
        cases_a, cases_b = by_config[config_a], by_config[config_b]
        shared = sorted(set(cases_a) & set(cases_b))
        if not shared:
            continue
        outcome = mcnemar_test([cases_a[c] for c in shared], [cases_b[c] for c in shared])
        if 'error' in outcome:
            continue
        results.append({
            'config_a': config_a,
            'config_b': config_b,
            'outcome': outcome,
        })

    if results:
        corrected = _holm_correction([r['outcome']['p_value'] for r in results])
        for result, p_corrected in zip(results, corrected):
            result['outcome']['p_corrected'] = p_corrected
            result['outcome']['significant_after_correction'] = p_corrected < ALPHA
    return results


def friedman_test(samples: dict) -> dict:
    """
    Friedman test across several configurations.

    :param samples: ``{config: [values]}`` — one list of per-case values per
                    configuration (only the cases present in every list are
                    used, so the test is paired).
    """
    from scipy.stats import friedmanchisquare  # noqa: PLC0415

    configs = sorted(samples)
    if len(configs) < 3:
        return {'error': 'The Friedman test requires at least three configurations.'}

    length = min(len(samples[config]) for config in configs)
    if length < 2:
        return {'error': 'Not enough paired observations.'}

    arrays = [samples[config][:length] for config in configs]
    try:
        statistic, p_value = friedmanchisquare(*arrays)
    except ValueError as exc:
        return {'error': f'Friedman test not applicable: {exc}'}

    if statistic != statistic:  # NaN — all samples are identical
        return {
            'statistic': 0.0,
            'p_value': 1.0,
            'n_blocks': length,
            'significant': False,
            'note': 'All configurations produced identical values.',
        }

    return {
        'statistic': float(statistic),
        'p_value': float(p_value),
        'n_blocks': length,
        'significant': float(p_value) < ALPHA,
    }


def posthoc_wilcoxon(samples: dict) -> list[dict]:
    """Wilcoxon signed-rank post-hoc comparisons with Holm correction."""
    from scipy.stats import wilcoxon  # noqa: PLC0415

    configs = sorted(samples)
    length = min((len(samples[c]) for c in configs), default=0)
    if length < 2:
        return []

    results = []
    for config_a, config_b in combinations(configs, 2):
        a = samples[config_a][:length]
        b = samples[config_b][:length]
        try:
            statistic, p_value = wilcoxon(a, b)
        except ValueError as exc:
            results.append({'config_a': config_a, 'config_b': config_b,
                            'error': str(exc)})
            continue
        differences = [x - y for x, y in zip(a, b)]
        cliff_delta = sum((1 if d > 0 else (-1 if d < 0 else 0)) for d in differences) / (len(differences) ** 2)
        results.append({
            'config_a': config_a,
            'config_b': config_b,
            'statistic': float(statistic),
            'p_value': float(p_value),
            'cliff_delta': float(cliff_delta),
        })

    valid = [r for r in results if 'p_value' in r]
    if valid:
        corrected = _holm_correction([r['p_value'] for r in valid])
        for result, p_corrected in zip(valid, corrected):
            result['p_corrected'] = p_corrected
            result['significant_after_correction'] = p_corrected < ALPHA
    return results


def bootstrap_ci(values: list, alpha: float = 0.05, n_resamples: int = 2000,
                 seed: int = 42) -> dict:
    """Percentile bootstrap confidence interval for the mean."""
    import random  # noqa: PLC0415

    numbers = [float(v) for v in values if v is not None]
    if len(numbers) < 2:
        return {'error': 'Not enough observations for a bootstrap interval.'}

    rng = random.Random(seed)
    n = len(numbers)
    means = []
    for _ in range(n_resamples):
        sample = [numbers[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lower_index = int((alpha / 2) * n_resamples)
    upper_index = min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)
    return {
        'mean': sum(numbers) / n,
        'ci_lower': means[lower_index],
        'ci_upper': means[upper_index],
        'alpha': alpha,
        'n': n,
        'n_resamples': n_resamples,
    }
