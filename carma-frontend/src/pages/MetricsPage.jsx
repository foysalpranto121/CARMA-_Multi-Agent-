import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, FlaskConical } from 'lucide-react';
import { metricsApi, experimentApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader,
  fmtNum, fmtPctValue,
} from '../components/ui';

export default function MetricsPage() {
  const [configFilter, setConfigFilter] = useState('');

  const configs = useQuery({
    queryKey: ['run-configs'],
    queryFn: async () => unwrap((await experimentApi.configurations({ page_size: 50 })).data),
  });

  const cost = useQuery({
    queryKey: ['cost-breakdown', configFilter],
    queryFn: async () => (await metricsApi.costBreakdown(
      configFilter ? { configuration: configFilter } : {})).data,
  });

  const scenarios = useQuery({
    queryKey: ['scenario-breakdown', configFilter],
    queryFn: async () => (await metricsApi.scenarioBreakdown(
      configFilter ? { configuration: configFilter } : {})).data,
  });

  const stats = useQuery({
    queryKey: ['statistical-tests', configFilter],
    queryFn: async () => (await metricsApi.statisticalTests(
      configFilter ? { configuration: configFilter } : {})).data,
  });

  const mcnemarRows = useMemo(() => {
    const s = stats.data;
    if (!s) return [];
    const rows = [];
    (s.mcnemar_violation_rate ?? []).forEach(e => rows.push({
      metric: 'Constraint violation rate', a: e.config_a, b: e.config_b,
      p: e.outcome?.p_value, significant: e.outcome?.significant_after_correction,
      odds: e.outcome?.odds_ratio,
    }));
    (s.mcnemar_task_success ?? []).forEach(e => rows.push({
      metric: 'Task success rate', a: e.config_a, b: e.config_b,
      p: e.outcome?.p_value, significant: e.outcome?.significant_after_correction,
      odds: e.outcome?.odds_ratio,
    }));
    return rows;
  }, [stats]);

  const bootstrapRows = useMemo(() => {
    const map = stats.data?.bootstrap_latency ?? {};
    return Object.entries(map).map(([code, value]) => ({ code, ...value }));
  }, [stats]);

  const configRows = cost.data ?? [];

  return (
    <div className="page-wrapper">
      <PageHeader
        title="METRICS & STATISTICS"
        subtitle="Real measured outcomes — no synthetic values. Every figure is computed from recorded adaptations."
        actions={(
          <select className="holo-select" value={configFilter}
                  onChange={(e) => setConfigFilter(e.target.value)}
                  aria-label="Filter by configuration">
            <option value="">All configurations</option>
            {(configs.data ?? []).map(c => (
              <option key={c.id} value={c.code}>{c.code} — {c.name}</option>
            ))}
          </select>
        )}
      />

      <div className="dashboard-grid">
        <div className="glass-card col-span-12">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            COST &amp; OUTCOME BY CONFIGURATION
          </div>
          {cost.isLoading ? <LoadingState /> : cost.error ? <ErrorState error={cost.error} onRetry={cost.refetch} /> : (
            <DataTable
              columns={[
                { key: 'code', header: 'CONFIG',
                  render: (r) => <Badge tone="cyan">{r.run__configuration__code}</Badge> },
                { key: 'tsr', header: 'TASK SUCCESS',
                  render: (r) => (r.mean_tsr === null ? '—' : fmtPctValue(r.mean_tsr * 100)) },
                { key: 'cvr', header: 'VIOLATION RATE',
                  render: (r) => (r.mean_cvr === null ? '—' : fmtPctValue(r.mean_cvr * 100)) },
                { key: 'viol', header: 'MEAN VIOL. COST',
                  render: (r) => (r.mean_viol === null ? '—' : r.mean_viol.toFixed(3)) },
                { key: 'exec', header: 'MEAN EXEC. COST',
                  render: (r) => (r.mean_exec === null ? '—' : r.mean_exec.toFixed(3)) },
              ]}
              rows={configRows}
              empty="No completed runs yet — run the experiment matrix first."
            />
          )}
        </div>

        <div className="glass-card col-span-6">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            McNemar — PAIRED COMPARISONS
          </div>
          {stats.isLoading ? <LoadingState /> : mcnemarRows.length === 0 ? (
            <EmptyState message="No paired comparisons available."
                        hint="McNemar needs both configurations to have solved the same case." />
          ) : (
            <DataTable
              columns={[
                { key: 'metric', header: 'METRIC',
                  render: (r) => (
                    <span style={{ fontFamily: 'var(--font-display)' }}>{r.metric}</span>
                  ) },
                { key: 'pair', header: 'PAIR',
                  render: (r) => `${r.a} vs ${r.b}` },
                { key: 'p', header: 'p-VALUE',
                  render: (r) => (r.p === null || r.p === undefined ? '—' : Number(r.p).toFixed(5)) },
                { key: 'or', header: 'ODDS RATIO',
                  render: (r) => (r.odds === null || r.odds === undefined ? '—'
                    : r.odds === Infinity ? '∞' : Number(r.odds).toFixed(3)) },
                { key: 'sig', header: 'RESULT',
                  render: (r) => (r.significant
                    ? <Badge tone="green">significant</Badge>
                    : <Badge tone="violet">n.s.</Badge>) },
              ]}
              rows={mcnemarRows}
            />
          )}
        </div>

        <div className="glass-card col-span-6">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            FRIEDMAN · LATENCY
          </div>
          {stats.isLoading ? <LoadingState /> : (
            <>
              {stats.data?.friedman_latency?.error ? (
                <EmptyState message={stats.data.friedman_latency.error} />
              ) : (
                <div className="flex items-center gap-lg" style={{ marginBottom: 'var(--space-md)' }}>
                  <div>
                    <div className="kpi-label">χ²</div>
                    <div className="kpi-value violet">
                      {Number(stats.data?.friedman_latency?.statistic ?? 0).toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="kpi-label">p-VALUE</div>
                    <div className="kpi-value gold">
                      {Number(stats.data?.friedman_latency?.p_value ?? 1).toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div className="kpi-label">VERDICT</div>
                    <div style={{ marginTop: 8 }}>
                      {stats.data?.friedman_latency?.significant
                        ? <Badge tone="green">significant</Badge>
                        : <Badge tone="violet">not significant</Badge>}
                    </div>
                  </div>
                </div>
              )}

              <div className="holo-subtitle" style={{ marginBottom: 8 }}>
                BOOTSTRAP 95% CI — MEAN LATENCY (s)
              </div>
              {bootstrapRows.length === 0 ? (
                <EmptyState message="No latency samples yet." />
              ) : (
                <DataTable
                  columns={[
                    { key: 'code', header: 'CONFIG',
                      render: (r) => <Badge tone="cyan">{r.code}</Badge> },
                    { key: 'mean', header: 'MEAN',
                      render: (r) => (r.mean === null || r.mean === undefined ? '—' : r.mean.toFixed(3)) },
                    { key: 'lo', header: 'CI LOW',
                      render: (r) => (r.ci_lower === null || r.ci_lower === undefined ? '—' : r.ci_lower.toFixed(3)) },
                    { key: 'hi', header: 'CI HIGH',
                      render: (r) => (r.ci_upper === null || r.ci_upper === undefined ? '—' : r.ci_upper.toFixed(3)) },
                    { key: 'n', header: 'N',
                      render: (r) => fmtNum(r.n) },
                  ]}
                  rows={bootstrapRows}
                />
              )}
            </>
          )}
        </div>

        <div className="glass-card col-span-12">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            PER-SCENARIO METRICS
          </div>
          {scenarios.isLoading ? <LoadingState /> : (
            <DataTable
              columns={[
                { key: 'config', header: 'CONFIG',
                  render: (r) => <Badge tone="cyan">{r.config_code}</Badge> },
                { key: 'scenario', header: 'SCENARIO',
                  render: (r) => <Badge tone="violet">{r.scenario_code}</Badge> },
                { key: 'tsr', header: 'TSR',
                  render: (r) => (r.tsr === null ? '—' : fmtPctValue(r.tsr * 100)) },
                { key: 'cvr', header: 'CVR',
                  render: (r) => (r.cvr === null ? '—' : fmtPctValue(r.cvr * 100)) },
                { key: 'conf', header: 'CONFORMANCE',
                  render: (r) => (r.conformance === null ? '—' : r.conformance.toFixed(3)) },
                { key: 'esc', header: 'ESCALATION',
                  render: (r) => (r.escalation_rate === null ? '—' : fmtPctValue(r.escalation_rate * 100)) },
                { key: 'lat', header: 'MEAN LAT.',
                  render: (r) => (r.mean_latency === null ? '—' : `${r.mean_latency.toFixed(2)}s`) },
                { key: 'p95', header: 'P95 LAT.',
                  render: (r) => (r.p95_latency === null ? '—' : `${r.p95_latency.toFixed(2)}s`) },
              ]}
              rows={scenarios.data ?? []}
              empty="No per-scenario metrics recorded yet."
            />
          )}
        </div>
      </div>
    </div>
  );
}
