import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { FlaskConical, Play } from 'lucide-react';
import { experimentApi, processApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader,
} from '../components/ui';
import { useAuthStore, hasRole } from '../store/authStore';

const SEEDS = [1, 2, 3];

export default function ExperimentNewPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canRun = hasRole(role, ['researcher']);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [configId, setConfigId] = useState('');
  const [processId, setProcessId] = useState('');
  const [constraintSetId, setConstraintSetId] = useState('');
  const [seed, setSeed] = useState(1);
  const [autoStart, setAutoStart] = useState(true);
  const [error, setError] = useState('');

  const configs = useQuery({
    queryKey: ['run-configs'],
    queryFn: async () => unwrap((await experimentApi.configurations({ page_size: 50 })).data),
  });

  const processes = useQuery({
    queryKey: ['processes'],
    queryFn: async () => unwrap((await processApi.list({ page_size: 100 })).data),
  });

  const constraintSets = useQuery({
    queryKey: ['constraint-sets', processId],
    queryFn: async () => unwrap((await processApi.constraintSets({
      process: processId, page_size: 50 })).data),
    enabled: Boolean(processId),
  });

  const create = useMutation({
    mutationFn: async () => {
      const payload = {
        configuration: configId,
        seed: Number(seed),
        ...(processId ? { process: processId } : {}),
        ...(constraintSetId ? { constraint_set: constraintSetId } : {}),
      };
      const res = await experimentApi.createRun(payload);
      const run = res.data;
      if (autoStart) {
        try {
          await experimentApi.start(run.id);
        } catch (err) {
          setError(err?.response?.data?.detail ?? 'Run created but could not be started.');
        }
      }
      return run;
    },
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
      navigate(`/experiments/${run.id}`);
    },
    onError: (err) => {
      const data = err?.response?.data;
      setError(data?.detail
        ?? (data && typeof data === 'object' ? JSON.stringify(data) : null)
        ?? err?.message ?? 'Could not create the run.');
    },
  });

  if (!canRun) {
    return (
      <div className="page-wrapper">
        <PageHeader title="NEW EXPERIMENT" subtitle="Configure a research run." />
        <EmptyState message="Your role cannot create experiment runs."
                    hint="Experiment creation requires the researcher or admin role." />
      </div>
    );
  }

  return (
    <div className="page-wrapper">
      <PageHeader
        title="NEW EXPERIMENT"
        subtitle="Configure one (configuration, seed) cell of the factorial study."
      />

      {error && (
        <div style={{ marginBottom: 'var(--space-md)', color: 'var(--holo-rose)', fontSize: 12 }}>
          {error}
        </div>
      )}

      <div className="dashboard-grid">
        <div className="glass-card col-span-5">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            CONFIGURATION MATRIX
          </div>
          {configs.isLoading ? <LoadingState /> : (
            <DataTable
              columns={[
                { key: 'code', header: 'CODE',
                  render: (r) => <Badge tone="cyan">{r.code}</Badge> },
                { key: 'name', header: 'NAME',
                  render: (r) => (
                    <span style={{ fontFamily: 'var(--font-display)' }}>{r.name}</span>
                  ) },
                { key: 'flags', header: 'COMPONENTS',
                  render: (r) => (
                    <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      {[
                        r.use_car ? 'CAR' : null,
                        r.use_scv ? 'SCV' : null,
                        r.multi_agent ? `MAS×${r.num_agents}` : null,
                      ].filter(Boolean).join(' · ') || 'baseline'}
                    </span>
                  ) },
              ]}
              rows={configs.data ?? []}
              empty="No configurations seeded. Run: python manage.py seed_configurations"
            />
          )}
        </div>

        <div className="glass-card col-span-7">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>RUN SETTINGS</div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
            <div>
              <label className="form-label" htmlFor="cfg">Configuration *</label>
              <select id="cfg" className="holo-select" value={configId}
                      onChange={(e) => setConfigId(e.target.value)}>
                <option value="">Select a configuration…</option>
                {(configs.data ?? []).map(c => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name} ({c.llm_model})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="form-label" htmlFor="proc">Process frame</label>
              <select id="proc" className="holo-select" value={processId}
                      onChange={(e) => {
                        setProcessId(e.target.value);
                        setConstraintSetId('');
                      }}>
                <option value="">None — use the benchmark process</option>
                {(processes.data ?? []).map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="form-label" htmlFor="cset">Constraint set</label>
              <select id="cset" className="holo-select" value={constraintSetId}
                      onChange={(e) => setConstraintSetId(e.target.value)}
                      disabled={!processId}>
                <option value="">None</option>
                {(constraintSets.data ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="form-label" htmlFor="seed">Random seed</label>
              <div className="flex items-center gap-sm">
                {SEEDS.map(s => (
                  <button key={s} type="button"
                          className={`btn ${seed === s ? 'btn-primary' : 'btn-ghost'}`}
                          style={{ fontSize: 11 }}
                          onClick={() => setSeed(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
                            color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={autoStart}
                     onChange={(e) => setAutoStart(e.target.checked)} />
              Start the run immediately after creation
            </label>

            <button
              className="btn btn-solid"
              disabled={!configId || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending
                ? <><span className="spinner" /> Creating…</>
                : <><Play size={13} /> Create &amp; start run</>}
            </button>

            <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              The run replays every validated benchmark case through the selected
              configuration with the selected seed. LLM sampling parameters come from
              the configuration record, so a run is reproducible given the same
              configuration, seed and model version.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
