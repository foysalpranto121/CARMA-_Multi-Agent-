import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Database, Upload, Search } from 'lucide-react';
import { benchmarkApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, Panel,
  fmtDate, fmtNum, fmtPctValue, toneFor,
} from '../components/ui';
import { useAuthStore, hasRole } from '../store/authStore';

export default function BenchmarkPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canImport = hasRole(role, ['researcher']);
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [scenarioFilter, setScenarioFilter] = useState('');
  const [notice, setNotice] = useState('');

  const scenarios = useQuery({
    queryKey: ['benchmark-scenarios'],
    queryFn: async () => unwrap((await benchmarkApi.scenarios({ page_size: 50 })).data),
  });

  const stats = useQuery({
    queryKey: ['benchmark-stats'],
    queryFn: async () => (await benchmarkApi.stats()).data,
  });

  const cases = useQuery({
    queryKey: ['benchmark-cases', scenarioFilter, search],
    queryFn: async () => unwrap((await benchmarkApi.cases({
      page_size: 100,
      ...(scenarioFilter ? { scenario: scenarioFilter } : {}),
      ...(search ? { search: search } : {}),
    })).data),
  });

  const importMutation = useMutation({
    mutationFn: (payload) => benchmarkApi.importLog(payload).then(r => r.data),
    onSuccess: (data) => {
      setNotice(`Import task started (${data.task_id ?? 'queued'}).`);
      queryClient.invalidateQueries({ queryKey: ['benchmark-cases'] });
    },
    onError: (err) => {
      setNotice(err?.response?.data?.detail ?? 'Import failed.');
    },
  });

  const byScenario = stats.data?.by_scenario ?? [];
  const total = stats.data?.total ?? 0;
  const validated = stats.data?.validated ?? 0;

  return (
    <div className="page-wrapper">
      <PageHeader
        title="WF-ADAPT BENCHMARK"
        subtitle="Annotated workflow-adaptation cases extracted from public BPI event logs."
        actions={canImport && (
          <button
            className="btn btn-solid"
            disabled={importMutation.isPending}
            onClick={() => {
              const logName = window.prompt('Event-log name to import (e.g. "BPI 2017")');
              if (logName) importMutation.mutate({ log_name: logName });
            }}
          >
            <Upload size={13} /> Import XES
          </button>
        )}
      />

      {notice && (
        <div style={{ marginBottom: 'var(--space-md)', fontSize: 12, color: 'var(--holo-cyan)' }}>
          {notice}
        </div>
      )}

      <div className="kpi-row" style={{ marginBottom: 'var(--space-lg)', gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Total Cases</span>
          <div className="kpi-value cyan">{fmtNum(total)}</div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Validated</span>
          <div className="kpi-value green">{fmtNum(validated)}</div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Scenarios</span>
          <div className="kpi-value violet">{fmtNum((scenarios.data ?? []).length)}</div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Mean κ</span>
          <div className="kpi-value gold">
            {fmtNum(
              byScenario.length
                ? byScenario.reduce((a, b) => a + (b.mean_kappa ?? 0), 0) / byScenario.length
                : null, 3)}
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="glass-card col-span-4">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>SCENARIOS</div>
          {scenarios.isLoading ? <LoadingState /> : (
            <DataTable
              columns={[
                { key: 'code', header: 'CODE',
                  render: (r) => <Badge tone="cyan">{r.code}</Badge> },
                { key: 'name', header: 'NAME',
                  render: (r) => (
                    <span style={{ fontFamily: 'var(--font-display)' }}>{r.name}</span>
                  ) },
                { key: 'count', header: 'CASES',
                  render: (r) => fmtNum(r.case_count) },
              ]}
              rows={scenarios.data ?? []}
              empty="No scenarios defined."
            />
          )}
        </div>

        <div className="glass-card col-span-8">
          <div className="flex items-center justify-between mb-md">
            <div className="holo-subtitle">CASES</div>
            <div className="flex items-center gap-sm">
              <select
                className="holo-select"
                value={scenarioFilter}
                onChange={(e) => setScenarioFilter(e.target.value)}
                aria-label="Filter by scenario"
              >
                <option value="">All scenarios</option>
                {(scenarios.data ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                ))}
              </select>
              <div className="input-wrapper" style={{ width: 180 }}>
                <Search size={13} className="input-icon" />
                <input
                  className="holo-input with-icon"
                  placeholder="Search case id…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>
          </div>

          {cases.isLoading ? <LoadingState label="Loading cases…" />
            : cases.error ? <ErrorState error={cases.error} onRetry={cases.refetch} />
            : (
            <DataTable
              columns={[
                { key: 'scenario', header: 'SCENARIO',
                  render: (r) => <Badge tone="cyan">{r.scenario_code}</Badge> },
                { key: 'case', header: 'CASE', render: (r) => r.case },
                { key: 'validated', header: 'VALIDATED',
                  render: (r) => (r.is_validated
                    ? <Badge tone="green">yes</Badge>
                    : <Badge tone="gold">no</Badge>) },
                { key: 'viol', header: 'GOLD VIOL.',
                  render: (r) => (r.gold_viol_cost ?? 0).toFixed(2) },
                { key: 'exec', header: 'GOLD EXEC.',
                  render: (r) => (r.gold_exec_cost ?? 0).toFixed(2) },
                { key: 'kappa', header: 'κ',
                  render: (r) => (r.kappa === null || r.kappa === undefined ? '—' : r.kappa.toFixed(3)) },
                { key: 'created', header: 'CREATED',
                  render: (r) => <span style={{ color: 'var(--text-muted)' }}>{fmtDate(r.created_at)}</span> },
              ]}
              rows={cases.data ?? []}
              empty="No benchmark cases match the current filter."
            />
          )}
        </div>
      </div>
    </div>
  );
}
