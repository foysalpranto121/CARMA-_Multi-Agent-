import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle } from 'lucide-react';
import { benchmarkApi, unwrap } from '../api/client';
import {
  Badge, DataTable, ErrorState, LoadingState, PageHeader, fmtNum,
} from '../components/ui';

const STRATEGIES = [
  { value: 'follow_observed_path',           label: 'Follow the observed path' },
  { value: 'take_observed_alternative_path', label: 'Take the observed alternative path' },
  { value: 'request_missing_document',       label: 'Request the missing document' },
  { value: 'apply_valid_rule_version',       label: 'Apply the rule version in force' },
  { value: 'escalate_for_approval',          label: 'Escalate for approval' },
  { value: 'map_renamed_activity',           label: 'Map the renamed activity' },
  { value: 'request_clarification',          label: 'Request clarification' },
  { value: 'resolve_by_authority',           label: 'Resolve by authority' },
  { value: 'escalate_conflict',              label: 'Escalate the conflict' },
  { value: 'ignore_injection',               label: 'Ignore the injected instruction' },
];

const fmtKappa = (value) => (value === null || value === undefined ? '—' : value.toFixed(3));

export default function AnnotationPage() {
  const queryClient = useQueryClient();
  const [scenario, setScenario] = useState('');
  const [selected, setSelected] = useState(null);
  const [strategy, setStrategy] = useState('');
  const [agrees, setAgrees] = useState(true);
  const [sequence, setSequence] = useState('');
  const [notes, setNotes] = useState('');
  const [notice, setNotice] = useState('');

  const scenarios = useQuery({
    queryKey: ['scenarios'],
    queryFn: async () => unwrap((await benchmarkApi.scenarios({ page_size: 50 })).data),
  });

  const filter = scenario ? { scenario } : {};

  const agreement = useQuery({
    queryKey: ['agreement', scenario],
    queryFn: async () => (await benchmarkApi.agreement({ ...filter, is_validated: true })).data,
  });

  const cases = useQuery({
    queryKey: ['annotation-cases', scenario],
    queryFn: async () => unwrap((await benchmarkApi.cases({
      ...filter, is_validated: true, page_size: 50,
    })).data),
  });

  const detail = useQuery({
    queryKey: ['benchmark-case', selected],
    queryFn: async () => (await benchmarkApi.case(selected)).data,
    enabled: Boolean(selected),
  });

  const annotations = useQuery({
    queryKey: ['annotations', selected],
    queryFn: async () => (await benchmarkApi.annotations(selected)).data,
    enabled: Boolean(selected),
  });

  // Start every case from its automated reference.
  const current = detail.data;
  useEffect(() => {
    if (!current) return;
    setStrategy(current.gold_adaptation?.strategy ?? '');
    setSequence((current.gold_activity_seq ?? []).join('\n'));
    setAgrees(true);
    setNotes('');
  }, [current?.id]);

  const submit = useMutation({
    mutationFn: (payload) => benchmarkApi.annotate(selected, payload).then((r) => r.data),
    onSuccess: () => {
      setNotice('Annotation recorded.');
      ['annotations', 'agreement', 'annotation-cases'].forEach((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }));
    },
    onError: (err) => setNotice(
      JSON.stringify(err?.response?.data ?? 'Could not record the annotation.')),
  });

  const stats = agreement.data ?? {};

  return (
    <div className="page-wrapper">
      <PageHeader
        title="GOLD ANNOTATION"
        subtitle="Two annotators check the reference of every case independently; Cohen's κ is computed over their strategy labels."
        actions={(
          <div className="flex items-center gap-sm">
            {[{ id: '', code: 'all' }, ...(scenarios.data ?? [])].map((s) => (
              <button key={s.id || 'all'}
                      className={`btn ${scenario === s.id ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ fontSize: 10, textTransform: 'uppercase' }}
                      onClick={() => { setScenario(s.id); setSelected(null); }}>
                {s.code}
              </button>
            ))}
          </div>
        )}
      />

      <div className="kpi-row" style={{ marginBottom: 'var(--space-lg)', gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Cohen's κ</span>
          <div className="kpi-value cyan">{fmtKappa(stats.kappa)}</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
            {stats.error ?? 'first two annotators, strategy labels'}
          </div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Observed agreement</span>
          <div className="kpi-value green">{fmtKappa(stats.observed_agreement)}</div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Double-annotated</span>
          <div className="kpi-value">{fmtNum(stats.double_annotated ?? 0)}</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
            {fmtNum(stats.annotated ?? 0)} cases with at least one annotation
          </div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Disagreements</span>
          <div className="kpi-value rose">{fmtNum((stats.disagreements ?? []).length)}</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
            resolve before the main runs
          </div>
        </div>
      </div>

      {notice && (
        <div style={{ marginBottom: 'var(--space-md)', fontSize: 12, color: 'var(--holo-cyan)' }}>
          {notice}
        </div>
      )}

      <div className="dashboard-grid">
        <div className="glass-card col-span-6">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            CASES ({fmtNum((cases.data ?? []).length)})
          </div>
          {cases.isLoading ? <LoadingState label="Loading cases…" />
            : cases.error ? <ErrorState error={cases.error} onRetry={cases.refetch} />
            : (
            <DataTable
              columns={[
                { key: 'case', header: 'CASE', render: (r) => r.case_id_str ?? '—' },
                { key: 'scenario', header: 'SCENARIO',
                  render: (r) => <Badge tone="violet">{r.scenario_code}</Badge> },
                { key: 'annotators', header: 'ANNOTATORS',
                  render: (r) => `${[r.annotator_1, r.annotator_2].filter(Boolean).length}/2` },
                { key: 'flag', header: '',
                  render: (r) => ((stats.disagreements ?? []).includes(r.id)
                    ? <Badge tone="rose">disagree</Badge> : null) },
                { key: 'actions', header: '',
                  render: (r) => (
                    <button className="btn btn-ghost" style={{ fontSize: 9 }}
                            onClick={() => { setSelected(r.id); setNotice(''); }}>
                      annotate
                    </button>
                  ) },
              ]}
              rows={cases.data ?? []}
              empty="No validated cases for this scenario."
            />
          )}
        </div>

        <div className="glass-card col-span-6">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            {current ? `CASE ${current.case_id_str} · ${current.scenario_code}` : 'SELECT A CASE'}
          </div>

          {!selected ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              Pick a case to check its reference adaptation.
            </div>
          ) : detail.isLoading ? <LoadingState /> : current && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
              <div>
                <div className="kpi-label">PERTURBATION</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {current.perturbation_text || current.perturbation?.description || '—'}
                </div>
              </div>
              <div>
                <div className="kpi-label">EXECUTED PREFIX (last 8 of {fmtNum((current.prefix_trace ?? []).length)})</div>
                <div className="mono-text" style={{ fontSize: 11, marginTop: 4 }}>
                  {(current.prefix_trace ?? []).slice(-8).map((e) => e.activity).join(' → ') || '—'}
                </div>
              </div>
              <div>
                <div className="kpi-label">AUTOMATED REFERENCE</div>
                <div style={{ marginTop: 4 }}>
                  <Badge tone="cyan">{current.gold_adaptation?.strategy ?? '—'}</Badge>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                  {current.gold_adaptation?.rationale}
                </div>
              </div>

              {(annotations.data ?? []).length > 0 && (
                <div>
                  <div className="kpi-label">ANNOTATIONS</div>
                  {(annotations.data ?? []).map((a) => (
                    <div key={a.id} style={{ fontSize: 11, marginTop: 4 }}>
                      {a.annotator_name || 'annotator'}: <Badge tone={a.agrees_with_reference ? 'green' : 'gold'}>{a.strategy}</Badge>
                    </div>
                  ))}
                </div>
              )}

              <div>
                <label className="form-label" htmlFor="strategy">Correct strategy</label>
                <select id="strategy" className="holo-select" value={strategy}
                        onChange={(e) => setStrategy(e.target.value)}>
                  {STRATEGIES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <label style={{ fontSize: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
                <input type="checkbox" checked={agrees} onChange={(e) => setAgrees(e.target.checked)} />
                The automated reference is correct
              </label>
              <div>
                <label className="form-label" htmlFor="sequence">Correct continuation (one activity per line)</label>
                <textarea id="sequence" className="holo-input mono-text" rows={5}
                          value={sequence} onChange={(e) => setSequence(e.target.value)} />
              </div>
              <div>
                <label className="form-label" htmlFor="notes">Notes</label>
                <textarea id="notes" className="holo-input" rows={2}
                          value={notes} onChange={(e) => setNotes(e.target.value)} />
              </div>
              <button className="btn btn-solid" style={{ justifyContent: 'center' }}
                      disabled={submit.isPending || !strategy}
                      onClick={() => submit.mutate({
                        strategy,
                        agrees_with_reference: agrees,
                        activity_seq: sequence.split('\n').map((s) => s.trim()).filter(Boolean),
                        notes,
                      })}>
                <CheckCircle size={13} /> Record annotation
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
