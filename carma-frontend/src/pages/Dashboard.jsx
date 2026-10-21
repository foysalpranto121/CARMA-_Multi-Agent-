import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import HoloOrb from '../components/HoloOrb';
import {
  Activity, ShieldX, Clock, CheckCircle, TriangleAlert,
  GitBranch, FlaskConical, Database, Cpu, Server,
} from 'lucide-react';
import {
  auditApi, benchmarkApi, experimentApi, metricsApi, systemApi, unwrap,
} from '../api/client';
import {
  Badge, EmptyState, ErrorState, LoadingState, MetricBar,
  fmtNum, fmtPctValue, fmtTime,
} from '../components/ui';

/* ── KPI Tile ───────────────────────────────────────────────── */
function KpiTile({ label, value, unit = '', color = 'cyan', icon: Icon, hint }) {
  return (
    <div className="glass-card kpi-tile">
      <div className="flex items-center justify-between mb-md">
        <span className="kpi-label">{label}</span>
        {Icon && (
          <div style={{
            width: 28, height: 28, borderRadius: 'var(--radius-sm)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid var(--border-dim)',
          }}>
            <Icon size={13} color={`var(--holo-${color})`} />
          </div>
        )}
      </div>
      <div className={`kpi-value ${color}`}>
        {value}{unit}
      </div>
      {hint && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
          {hint}
        </div>
      )}
    </div>
  );
}

const NODE_INFO = {
  car:  { title: 'Constraint-Aware Retriever', color: 'cyan',
          desc: 'Filters evidence by process state, timestamp validity and reachability. Score = α·sim + β·prox + γ·match.' },
  scv:  { title: 'Symbolic Constraint Verifier', color: 'violet',
          desc: 'Checks alignment cost, Declare automata, policy predicates and cross-agent conflicts before issuing a plan token.' },
  plan: { title: 'LangGraph Planner', color: 'gold',
          desc: 'Produces schema-validated adaptation plans. Must cite evidence provenance IDs. Reports self-assessed confidence.' },
  exec: { title: 'ReAct Executor', color: 'green',
          desc: 'Least-privilege MCP tool agent. Write tools only unlock with a valid SCV-signed plan token.' },
};

/* ── Main Dashboard ─────────────────────────────────────────── */
export default function Dashboard() {
  const [activeNode, setActiveNode] = useState(null);

  const status = useQuery({
    queryKey: ['system-status'],
    queryFn: async () => (await systemApi.status()).data,
    refetchInterval: 30_000,
  });

  const benchStats = useQuery({
    queryKey: ['benchmark-stats'],
    queryFn: async () => (await benchmarkApi.stats()).data,
  });

  const runs = useQuery({
    queryKey: ['runs', 'overview'],
    queryFn: async () => unwrap((await experimentApi.runs({ page_size: 100 })).data),
  });

  const configs = useQuery({
    queryKey: ['run-configs'],
    queryFn: async () => unwrap((await experimentApi.configurations({ page_size: 50 })).data),
  });

  const results = useQuery({
    queryKey: ['run-results', 'overview'],
    queryFn: async () => unwrap((await experimentApi.results({ page_size: 200 })).data),
  });

  const scenarios = useQuery({
    queryKey: ['scenario-breakdown'],
    queryFn: async () => (await metricsApi.scenarioBreakdown()).data,
  });

  const stats = useQuery({
    queryKey: ['statistical-tests'],
    queryFn: async () => (await metricsApi.statisticalTests()).data,
  });

  const audit = useQuery({
    queryKey: ['audit-stream'],
    queryFn: async () => unwrap((await auditApi.entries({ page_size: 15, ordering: '-sequence_num' })).data),
    refetchInterval: 10_000,
  });

  /* ── Derived aggregates (all from live data) ── */
  const runRows   = runs.data ?? [];
  const cfgRows   = configs.data ?? [];
  const resRows   = results.data ?? [];
  const counts    = status.data?.counts ?? {};

  const runStats = useMemo(() => ({
    total:     runRows.length,
    completed: runRows.filter(r => r.status === 'completed').length,
    running:   runRows.filter(r => r.status === 'running').length,
    failed:    runRows.filter(r => r.status === 'failed').length,
  }), [runRows]);

  const activeRun = useMemo(
    () => runRows.find(r => r.status === 'running')
        ?? runRows.find(r => r.status === 'pending')
        ?? null,
    [runRows],
  );

  const meanTsv = useMemo(() => {
    const values = resRows.map(r => r.task_success_rate).filter(v => v !== null && v !== undefined);
    if (!values.length) return null;
    return values.reduce((a, b) => a + b, 0) / values.length;
  }, [resRows]);

  const meanCvr = useMemo(() => {
    const values = resRows.map(r => r.constraint_viol_rate).filter(v => v !== null && v !== undefined);
    if (!values.length) return null;
    return values.reduce((a, b) => a + b, 0) / values.length;
  }, [resRows]);

  const meanLatency = useMemo(() => {
    const values = resRows.map(r => r.mean_latency_s).filter(v => v !== null && v !== undefined);
    if (!values.length) return null;
    return values.reduce((a, b) => a + b, 0) / values.length;
  }, [resRows]);

  /* Per-configuration aggregation from the real run results */
  const perConfig = useMemo(() => {
    const map = new Map();
    resRows.forEach((r) => {
      const code = r.run?.configuration?.code
        ?? r.run?.configuration
        ?? r.config_code;
      if (!code) return;
      if (!map.has(code)) map.set(code, { tsr: [], cvr: [], latency: [] });
      const bucket = map.get(code);
      if (r.task_success_rate !== null && r.task_success_rate !== undefined) bucket.tsr.push(r.task_success_rate);
      if (r.constraint_viol_rate !== null && r.constraint_viol_rate !== undefined) bucket.cvr.push(r.constraint_viol_rate);
      if (r.mean_latency_s !== null && r.mean_latency_s !== undefined) bucket.latency.push(r.mean_latency_s);
    });
    const mean = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
    const out = {};
    map.forEach((bucket, code) => {
      out[code] = { tsr: mean(bucket.tsr), cvr: mean(bucket.cvr), latency: mean(bucket.latency) };
    });
    return out;
  }, [resRows]);

  const matrixRows = useMemo(() => {
    const codes = cfgRows.length
      ? cfgRows.map(c => c.code)
      : ['B0', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7'];
    return codes.map((code) => {
      const cfg = cfgRows.find(c => c.code === code);
      const agg = perConfig[code] ?? {};
      return {
        code,
        name: cfg?.name ?? code,
        car: cfg?.use_car ?? false,
        scv: cfg?.use_scv ?? false,
        agents: cfg?.num_agents ?? 0,
        tsr: agg.tsr ?? null,
        cvr: agg.cvr ?? null,
      };
    });
  }, [cfgRows, perConfig]);

  /* Scenario aggregation across configurations */
  const scenarioRows = useMemo(() => {
    const list = scenarios.data ?? [];
    const map = new Map();
    list.forEach((row) => {
      const key = row.scenario_code;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(row);
    });
    return [...map.entries()].map(([code, rows]) => {
      const mean = (field) => {
        const values = rows.map(r => r[field]).filter(v => v !== null && v !== undefined);
        return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
      };
      return { code, cvr: mean('cvr'), tsr: mean('tsr'), n: rows.length };
    }).sort((a, b) => a.code.localeCompare(b.code));
  }, [scenarios]);

  const statRows = useMemo(() => {
    const s = stats.data;
    if (!s || !s.n_adaptations) return [];
    const rows = [];
    (s.mcnemar_violation_rate ?? []).forEach((entry) => {
      const o = entry.outcome ?? {};
      rows.push({
        test: `McNemar · violation rate · ${entry.config_a} vs ${entry.config_b}`,
        stat: o.p_value != null ? `p=${Number(o.p_value).toFixed(4)}` : '—',
        p: o.significant_after_correction ? 'significant' : 'n.s.',
        sig: Boolean(o.significant_after_correction),
      });
    });
    (s.mcnemar_task_success ?? []).forEach((entry) => {
      const o = entry.outcome ?? {};
      rows.push({
        test: `McNemar · task success · ${entry.config_a} vs ${entry.config_b}`,
        stat: o.p_value != null ? `p=${Number(o.p_value).toFixed(4)}` : '—',
        p: o.significant_after_correction ? 'significant' : 'n.s.',
        sig: Boolean(o.significant_after_correction),
      });
    });
    if (s.friedman_latency && !s.friedman_latency.error) {
      rows.push({
        test: 'Friedman · latency across configurations',
        stat: `χ²=${Number(s.friedman_latency.statistic ?? 0).toFixed(2)}`,
        p: `p=${Number(s.friedman_latency.p_value ?? 1).toFixed(4)}`,
        sig: Boolean(s.friedman_latency.significant),
      });
    }
    (s.posthoc_latency ?? []).forEach((entry) => {
      rows.push({
        test: `Wilcoxon · latency · ${entry.config_a} vs ${entry.config_b}`,
        stat: entry.p_value != null ? `p=${Number(entry.p_value).toFixed(4)}` : '—',
        p: entry.significant_after_correction ? 'significant' : 'n.s.',
        sig: Boolean(entry.significant_after_correction),
      });
    });
    return rows;
  }, [stats]);

  const componentStatus = useMemo(() => {
    const s = status.data;
    if (!s) return [];
    return [
      { icon: Server,  label: 'API',      value: s.status === 'ok' ? 'ONLINE' : 'DEGRADED',
        color: s.status === 'ok' ? 'var(--holo-green)' : 'var(--holo-gold)' },
      { icon: Database, label: 'Database', value: (s.database ?? 'unknown').toUpperCase(),
        color: s.database === 'ok' ? 'var(--holo-green)' : 'var(--holo-rose)' },
      { icon: Cpu,     label: 'LLM',      value: s.llm?.configured
          ? `${s.llm.provider.toUpperCase()}${s.llm.reachable === false ? ' · DOWN' : ''}`
          : 'NOT CONFIGURED',
        color: s.llm?.configured
          ? (s.llm.reachable === false ? 'var(--holo-gold)' : 'var(--holo-cyan)')
          : 'var(--holo-rose)' },
      { icon: GitBranch, label: 'Vector store',
        value: s.vector_store?.reachable ? 'REACHABLE'
             : s.vector_store?.configured ? 'UNREACHABLE' : 'NOT CONFIGURED',
        color: s.vector_store?.reachable ? 'var(--holo-violet)' : 'var(--holo-rose)' },
    ];
  }, [status]);

  const isLoading = status.isLoading || runs.isLoading || configs.isLoading;
  const loadError = status.error ?? runs.error ?? configs.error;

  if (loadError) {
    return (
      <div className="page-wrapper">
        <ErrorState error={loadError}
                    onRetry={() => { status.refetch(); runs.refetch(); configs.refetch(); }} />
      </div>
    );
  }

  return (
    <div className="page-wrapper">

      {/* ── Orb Hero ── */}
      <div className="orb-hero" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="orb-hero-left">
          <HoloOrb
            onNodeClick={setActiveNode}
            activeNode={activeNode}
            violationCount={counts.escalations_pending ?? 0}
          />
        </div>

        <div className="orb-hero-right">
          <div>
            <div className="holo-subtitle" style={{ marginBottom: 8 }}>
              CONSTRAINT-AWARE MULTI-AGENT WORKFLOW ADAPTATION
            </div>
            <h1 className="holo-title orb-hero-title">CARMA</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 12, maxWidth: 500, lineHeight: 1.7 }}>
              Two constraint layers — retrieval-side (CAR) and action-side (SCV) — wrap a
              4-agent LangGraph team running on public BPI event logs across 8 configurations
              and 3 LLMs. Click an orbital node to inspect the component.
            </p>
          </div>

          {activeNode && NODE_INFO[activeNode] && (
            <div className={`glass-card accent-${NODE_INFO[activeNode].color}`}
                 style={{ padding: 'var(--space-md)', animation: 'card-appear 0.3s ease both' }}>
              <div className="flex items-center gap-sm mb-md">
                <Badge tone={NODE_INFO[activeNode].color}>{activeNode.toUpperCase()}</Badge>
                <span style={{ fontSize: 13, fontWeight: 600 }}>
                  {NODE_INFO[activeNode].title}
                </span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {NODE_INFO[activeNode].desc}
              </p>
              <button className="btn btn-ghost" style={{ marginTop: 12, fontSize: 10 }}
                      onClick={() => setActiveNode(null)}>
                DISMISS
              </button>
            </div>
          )}

          <div className="orb-status-grid">
            {componentStatus.map((s) => (
              <div key={s.label} className="orb-status-item">
                <span className="orb-status-icon"
                      style={{ background: s.color, boxShadow: `0 0 6px ${s.color}` }} />
                <span style={{ color: 'var(--text-muted)', minWidth: 86 }}>{s.label}</span>
                <span style={{ color: s.color, fontWeight: 600 }}>{s.value}</span>
              </div>
            ))}
          </div>

          <div className="flex gap-sm">
            <Link to="/experiments/new" className="btn btn-solid" style={{ textDecoration: 'none' }}>
              <FlaskConical size={13} /> New Experiment
            </Link>
            <Link to="/benchmark" className="btn btn-primary" style={{ textDecoration: 'none' }}>
              <GitBranch size={13} /> View Benchmark
            </Link>
          </div>
        </div>
      </div>

      {/* ── KPI Row ── */}
      <div className="kpi-row" style={{ marginBottom: 'var(--space-lg)' }}>
        <KpiTile label="Benchmark Cases" value={fmtNum(counts.benchmark_cases ?? benchStats.data?.total ?? 0)}
                 color="cyan" icon={Activity}
                 hint={`${fmtNum(benchStats.data?.validated ?? 0)} validated`} />
        <KpiTile label="Task Success" value={meanTsv === null ? '—' : fmtPctValue(meanTsv * 100)}
                 color="green" icon={CheckCircle}
                 hint={`${fmtNum(runStats.completed)} completed runs`} />
        <KpiTile label="Violation Rate" value={meanCvr === null ? '—' : fmtPctValue(meanCvr * 100)}
                 color="rose" icon={ShieldX}
                 hint={`${fmtNum(runStats.total)} runs registered`} />
        <KpiTile label="Pending Escalations" value={fmtNum(counts.escalations_pending ?? 0)}
                 color="gold" icon={TriangleAlert}
                 hint={`${fmtNum(counts.adaptations ?? 0)} adaptations recorded`} />
        <KpiTile label="Avg Latency" value={meanLatency === null ? '—' : meanLatency.toFixed(2)}
                 unit="s" color="violet" icon={Clock}
                 hint={activeRun ? `run ${activeRun.config_code} in progress` : 'no active run'} />
      </div>

      {/* ── Main grid ── */}
      <div className="dashboard-grid">

        {/* Configuration matrix */}
        <div className="glass-card col-span-7" style={{ animationDelay: '100ms' }}>
          <div className="flex items-center justify-between mb-lg">
            <div>
              <div className="holo-subtitle" style={{ marginBottom: 4 }}>CONFIGURATION MATRIX</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                B0–B7 · Constraint Violation Rate vs Task Success Rate
              </div>
            </div>
            <Badge tone="cyan">2×2 Factorial</Badge>
          </div>

          {isLoading ? <LoadingState label="Loading configurations…" /> : (
            <div className="config-matrix">
              <div className="config-row"
                   style={{ color: 'var(--text-muted)', fontSize: 10, letterSpacing: '0.1em' }}>
                <span>CODE</span>
                <span>CONFIGURATION</span>
                <span>CAR</span>
                <span>SCV</span>
                <span>CVR↓</span>
                <span>TSR↑</span>
              </div>

              {matrixRows.map((c) => (
                <div key={c.code}
                     className={`config-row ${c.code === 'B7' ? 'highlighted' : ''}`}>
                  <div className="config-badge">
                    <span className="glow-text-cyan">{c.code}</span>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{c.name}</span>
                  <span style={{ fontSize: 11, color: c.car ? 'var(--holo-cyan)' : 'var(--text-muted)' }}>
                    {c.car ? '✓ ON' : '✗ OFF'}
                  </span>
                  <span style={{ fontSize: 11, color: c.scv ? 'var(--holo-violet)' : 'var(--text-muted)' }}>
                    {c.scv ? '✓ ON' : '✗ OFF'}
                  </span>
                  <span className="mono-text"
                        style={{ color: c.cvr === null ? 'var(--text-muted)'
                                 : c.cvr < 0.15 ? 'var(--holo-green)'
                                 : c.cvr > 0.25 ? 'var(--holo-rose)' : 'var(--holo-gold)' }}>
                    {c.cvr === null ? '—' : fmtPctValue(c.cvr * 100)}
                  </span>
                  <span className="mono-text"
                        style={{ color: c.tsr === null ? 'var(--text-muted)'
                                 : c.tsr > 0.8 ? 'var(--holo-green)' : 'var(--text-secondary)' }}>
                    {c.tsr === null ? '—' : fmtPctValue(c.tsr * 100)}
                  </span>
                </div>
              ))}
              {matrixRows.length === 0 && (
                <EmptyState message="No configurations seeded yet."
                            hint="Run: python manage.py seed_configurations" />
              )}
            </div>
          )}
        </div>

        {/* Audit stream */}
        <div className="glass-card col-span-5" style={{ animationDelay: '150ms' }}>
          <div className="flex items-center justify-between mb-md">
            <div className="holo-subtitle">AUDIT STREAM</div>
            <Badge tone="green">
              <span style={{ width: 5, height: 5, borderRadius: '50%',
                             background: 'var(--holo-green)', display: 'inline-block' }} />
              LIVE
            </Badge>
          </div>

          {activeRun && (
            <div className="metric-bar-wrap" style={{ marginBottom: 'var(--space-md)' }}>
              <div className="metric-bar-label">
                <span>Run progress · {activeRun.config_code} · seed={activeRun.seed}</span>
                <span className="mono-text">{activeRun.progress_pct ?? 0}%</span>
              </div>
              <div className="metric-bar-track">
                <div className="metric-bar-fill cyan" style={{ width: `${activeRun.progress_pct ?? 0}%` }} />
              </div>
            </div>
          )}

          {audit.isLoading ? <LoadingState label="Loading audit entries…" /> : (
            <div className="log-terminal">
              {(audit.data ?? []).map((entry) => (
                <div key={entry.id} className="log-entry">
                  <span className="log-time">{fmtTime(entry.timestamp)}</span>
                  <span className="log-type">{String(entry.entry_type ?? '').toUpperCase().slice(0, 8)}</span>
                  <span className="log-msg">
                    {entry.actor_name ?? entry.actor_agent ?? 'system'}
                    {entry.payload ? ` — ${JSON.stringify(entry.payload).slice(0, 120)}` : ''}
                  </span>
                </div>
              ))}
              {(audit.data ?? []).length === 0 && (
                <div style={{ color: 'var(--text-muted)' }}>
                  No audit entries yet — run an experiment to populate the chain.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Research questions */}
        <div className="glass-card col-span-12" style={{ animationDelay: '200ms' }}>
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>RESEARCH QUESTIONS</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 'var(--space-md)' }}>
            {[
              { rq:'RQ1', color:'cyan',   h:'H1', title:'Constraint-Aware Retrieval', metric:'Procedural precision@k · Stage accuracy · Macro-F1', compare:'CAR vs Vector RAG vs GraphRAG' },
              { rq:'RQ2', color:'violet', h:'H2', title:'Pre-Exec Symbolic Verification', metric:'CVR · Violation cost · p95 latency', compare:'B4 vs B6 (SCV on/off)' },
              { rq:'RQ3', color:'gold',   h:'H3', title:'Complementary Mechanisms', metric:'TSR · Conformance fitness · Per-scenario', compare:'B4–B7 factorial interaction' },
              { rq:'RQ4', color:'green',  h:'H4', title:'Scaffolding for Small Models', metric:'Config × model interaction', compare:'8B vs 30B vs Frontier' },
            ].map(r => (
              <div key={r.rq} className={`glass-card rq-card accent-${r.color}`}
                   style={{ padding: 'var(--space-md)', margin: 0 }}>
                <div className="rq-number" style={{ color: `var(--holo-${r.color})` }}>{r.rq}</div>
                <div className="rq-tag">{r.rq}</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{r.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 8 }}>
                  {r.metric}
                </div>
                <Badge tone={r.color} style={{ fontSize: 9 }}>{r.compare}</Badge>
              </div>
            ))}
          </div>
        </div>

        {/* Per-configuration metrics */}
        <div className="glass-card col-span-4" style={{ animationDelay: '250ms' }}>
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            KEY METRICS BY CONFIGURATION
          </div>
          {resRows.length === 0 ? (
            <EmptyState message="No completed run results yet."
                        hint="Metrics appear once a run finishes." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
              {matrixRows.filter(c => c.tsr !== null || c.cvr !== null).map(c => (
                <MetricBar
                  key={c.code}
                  label={`${c.code} · task success`}
                  value={c.tsr === null ? 0 : c.tsr * 100}
                  display={c.tsr === null ? '—' : fmtPctValue(c.tsr * 100)}
                  color="green"
                />
              ))}
            </div>
          )}
        </div>

        {/* Scenario breakdown */}
        <div className="glass-card col-span-4" style={{ animationDelay: '300ms' }}>
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>SCENARIO BREAKDOWN</div>
          {scenarioRows.length === 0 ? (
            <EmptyState message="No per-scenario metrics yet." />
          ) : (
            scenarioRows.map(s => (
              <div key={s.code} className="flex items-center gap-md" style={{ marginBottom: 10 }}>
                <Badge tone="cyan" style={{ width: 34, justifyContent: 'center' }}>{s.code}</Badge>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)', flex: 1 }}>
                  {s.n} measurement{s.n === 1 ? '' : 's'}
                </span>
                <div style={{ width: 80 }}>
                  <div className="metric-bar-track">
                    <div className="metric-bar-fill rose"
                         style={{ width: `${Math.min(100, (s.cvr ?? 0) * 100)}%` }} />
                  </div>
                </div>
                <span className="mono-text" style={{ width: 52, textAlign: 'right', color: 'var(--holo-rose)' }}>
                  {s.cvr === null ? '—' : fmtPctValue(s.cvr * 100)}
                </span>
              </div>
            ))
          )}
        </div>

        {/* Statistical tests */}
        <div className="glass-card col-span-4" style={{ animationDelay: '350ms' }}>
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>STATISTICAL TESTS</div>
          {stats.isLoading ? <LoadingState /> : statRows.length === 0 ? (
            <EmptyState message="No statistical tests could be computed yet."
                        hint="Tests need paired adaptation results across configurations." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
              {statRows.map((t, i) => (
                <div key={i} className="flex items-center gap-sm"
                     style={{ padding: '6px 8px', borderRadius: 'var(--radius-sm)',
                              background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-dim)' }}>
                  <span style={{ flex: 1, fontSize: 11, color: 'var(--text-secondary)' }}>{t.test}</span>
                  <span className="mono-text" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{t.stat}</span>
                  <Badge tone={t.sig ? 'green' : 'violet'} style={{ fontSize: 9 }}>{t.p}</Badge>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
