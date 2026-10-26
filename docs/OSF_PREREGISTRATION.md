# CARMA — OSF Preregistration

**Title.** Constraint-Aware Retrieval and Verification for Multi-Agent Workflow Adaptation: a controlled factorial study on WF-Adapt
**Authors.** Foysal Ahmed Pranto
**Registration.** https://osf.io/fv2ry/ — registered 2026-10-26 (template "OSF Preregistration"), embargoed until 2027-10-26, before any evaluation-split run of a registered model. The submitted field text is `docs/OSF_REGISTRATION_FORM.md`; where this protocol and the registered fields differ, the registered fields hold.

---

## 1. Research questions and hypotheses

- **RQ1 — retrieval side.** Does constraint-aware retrieval (CAR) reduce constraint violations and improve task success compared with plain vector retrieval?
- **RQ2 — action side.** Does a symbolic constraint verifier (SCV) that gates execution reduce constraint violations?
- **RQ3 — interaction.** Do CAR and SCV interact?
- **RQ4 — model size.** Does the reliability gain depend on the size of the model?

| | Hypothesis | Test |
|---|---|---|
| **H1** | CAR yields higher procedural precision@k and stage accuracy, and fewer downstream violations, than vector retrieval (B5 vs B4). | McNemar on violations; mixed-effects main effect of CAR |
| **H2** | The SCV lowers the constraint-violation rate relative to an unconstrained team (B6 vs B4). The confidence gate keeps its latency overhead bounded. | McNemar on violations; Friedman/Wilcoxon on latency |
| **H3** | CAR and SCV interact positively; full CARMA (B7) has the lowest violation rate among the LLM configurations. | CAR × SCV term of the mixed model; B7–B5 and B7–B6 contrasts |
| *exploratory* | The rule-based baseline B0 is best on unperturbed cases (S0) and fails under rule change (S2) and drift (S3). Exploratory because B0's outcomes were observed before registration (Section 3). | per-scenario contrasts |
| **H4** | The reliability gain of CARMA over the unconstrained team (B7 vs B4) is larger for the smaller model. | configuration × model term of the mixed model |

## 2. Design

A controlled repeated-measures experiment. Every configuration runs on the same benchmark cases; cases are the unit of pairing.

| Code | Configuration | Retrieval | Agents | Verifier acts | Escalation gate |
|---|---|---|---|---|---|
| B0 | Rule-based baseline | — | — (deterministic) | — | — |
| B1 | Single LLM | — | 1 | — | — |
| B2 | Single LLM + vector RAG | vector | 1 | — | — |
| B3 | Single LLM + GraphRAG | graph | 1 | — | — |
| B4 | Team + vector RAG | vector | 4 | — | — |
| B5 | Team + CAR | constraint-aware | 4 | — | — |
| B6 | Team + vector RAG + SCV | vector | 4 | yes | — |
| B7 | CARMA full | constraint-aware | 4 | yes | yes |

B4–B7 form the 2 × 2 factorial {CAR, SCV}. In B6/B7 a plan the verifier rejects returns to the planner with the violation report, at most *k* times; a plan still rejected does not run (B6) or is escalated (B7). The verifier also *scores* every configuration's plan so that violation rates are comparable; scoring never changes what runs.

**Models.** Two open-weight models of one family, run on the Groq free tier: **gpt-oss-20b** (small) and **gpt-oss-120b** (large) — the same training recipe at two sizes isolates the size contrast of H4. The served model version is recorded per call. Both run with reasoning effort *low*: the hidden reasoning tokens count against the free tier's daily quota (200 000 tokens per model), and *low* cuts a case's tokens about threefold (pilot measurement: 15.6–18.8 k → 4.7–6.8 k tokens per B7 case). The effort is the same for every configuration and stored with each configuration. No paid API model is part of the study.
**Sampling.** Temperature 0.2; seed 42 for the registered runs. Seeds 43 and 44 are run on B4 and B7 afterwards as an exploratory check of run-to-run variation, as far as the free quota allows.
**Prompts.** Identical across configurations; a configuration differs only in its components. In an SCV repair round the planner receives the verifier's report; the coordinator's framing of the case is not recomputed, because the case it frames has not changed.
**Execution.** The configurations of a model run case-major — every configuration runs a case before the next case starts — so that a change of the hosted model during the weeks of the study affects all configurations alike.

## 3. Data — the WF-Adapt benchmark

**Event logs.** Four public logs, each split 70 % training / 30 % test by case start time:

| Key | Log | Domain |
|---|---|---|
| bpi2017 | BPI Challenge 2017 (doi:10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b) | loan origination |
| bpi2020 | BPI Challenge 2020, travel permits (doi:10.4121/uuid:52fb97d4-4588-43c9-9d04-3604d4613b51) | travel expenses |
| rtfm | Road Traffic Fine Management (doi:10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5) | public administration |
| helpdesk | Helpdesk, Polato 2017 (doi:10.17632/39bp3vv62t.1) | IT service management |

The process model (Inductive Miner), the Declare and policy constraints and the knowledge corpus are built from the **training** split only; benchmark cases come from the **test** split only.

**Scenarios.** S0 nominal · S1 exception (missing document) · S2 rule change (version in force or not yet in force) · S3 structural drift (renamed activity) · S4 ambiguous request · S5 conflicting intents · S6 adversarial instruction.

**Case selection.** Per log and scenario, 30 evaluation cases are drawn by a seeded shuffle (seed 42) from the test split. A case is used only if its observed continuation complies with the mined frame, because the observed continuation is the reference of S0, S3, S5 and S6 and an unreachable reference could not be scored. The next case in the seeded order replaces a skipped one. Each case receives an automated reference (strategy and activity sequence); a reference may break the frame only in S1, where the cheapest non-compliant path is the right answer when no compliant one exists.

**Size.** 840 evaluation cases built, 835 validated (5 Helpdesk cases use activities the discovered model does not contain), **807 in the evaluation split**: the 28 cases on which a model had been run before registration (retired gpt-4o pilots, see *Foreknowledge*) were moved to a split that is never evaluated; their ids are in `artifacts/preregistration/seen_cases.json`. A separate **pilot split** of 84 cases (3 per log and scenario, the next ones in the same seeded order) is used only for tuning (Section 5) and never evaluated.

**Confirmatory sample.** The LLM configurations run on **196 evaluation cases: 7 per log × scenario cell** (28 per scenario, 49 per log), the first 7 of each cell in case-id order (case ids are random UUIDs, so the choice is blind to outcomes; every cell keeps ≥ 27 cases after the exclusion). The size follows from the power analysis (Section 6) and the free quota: B4–B7 cost ≈ 15 k tokens per case per model, so the 196 cases take about two weeks per model. B0 uses no model and runs on all 835 cases; its comparisons with the LLM configurations use the 196 cases they share.

**Foreknowledge.** Before registration the authors observed: the four public event logs and the benchmark built from them (cases and automated references, while validating the builder); the outcomes of the rule-based baseline B0 (no model, deterministic) on all evaluation cases — overall task success 0.296 and violation rate 0.067 — while validating the scoring rules; outcomes of retired pilot runs of B4 and B7 with `gpt-4o` on 28 evaluation cases, which revealed a contradictory planner rule and a missing goal definition that were then fixed (those 28 cases are excluded); and B7 runs of both registered models on the pilot split, for τ tuning and a token-usage measurement. No outcome of a registered model on an evaluation case exists: the software refuses to run an LLM configuration on the evaluation split until the registration URL is recorded, and records it with every run.

**References.** Before analysis the first author audits the automated references of a random 20 % of the confirmatory cases (stratified by scenario, seed 42) on the platform's Annotate page, which shows the case and its reference but no configuration output; the share of rejected references is reported and a rejected reference's case is excluded from every configuration.

## 4. Variables

| Outcome | Definition |
|---|---|
| Constraint-violation rate (CVR) — **primary** | share of cases whose **executed** trace violates at least one hard constraint; a blocked, declined or escalated plan executes nothing |
| Task success rate (TSR) — **primary** | the goal is reached with no hard violation. Goal: the executed continuation ends with an end activity of the process (those its training traces end with) or with the reference's last activity; for the strategies that leave the case to a human (escalate for approval, request clarification, escalate the conflict) the goal is reached when the system escalated or the agent declined |
| Adaptation correctness | exact match with the reference sequence; 2·LCS similarity (partial match ≥ 0.5) |
| Unsafe-action rate | a hard-violating write action executed |
| Escalation rate | share of cases handed to a human |
| Retrieval | of the k documents in a case's evidence pack: *procedural precision@k* = share that refer to an activity enabled in the case's current state or required by its scenario frame and are not marked superseded or not yet in force for the case; *stage accuracy* = share whose stage equals the case's current stage. Computed after the runs from the stored evidence packs and the deterministic state estimate |
| Efficiency | p50/p95 latency, tokens, LLM calls, list-price cost |

A case whose model call fails after the retries is recorded as failed and counts as not successful; failures are reported per configuration.

## 5. Tuning (pilot split only)

- **Tuned:** the escalation threshold τ of B7 only. B7 runs once on the pilot split with the confidence gate off; every τ ∈ {0.0, 0.1, …, 0.9} is replayed offline (a plan whose confidence is below τ would have been escalated); the τ with the highest pilot TSR is chosen, ties going to the smaller τ. The chosen value and the full grid are recorded in `artifacts/tuning/tau_<model>.json` and fixed before the main runs. τ is tuned separately for each model, because each model's confidences are calibrated differently.
- **Fixed at their defaults:** α = 0.6, β = 0.2, γ = 0.2 (CAR score weights), k = 3 repair rounds, top-k = 10.

## 6. Analysis plan

- **Confirmatory contrasts** on binary outcomes (violation, success), per model: B5–B4 (H1), B6–B4 (H2), B7–B4, B7–B5 and B7–B6 (H3) — 5 contrasts × 2 outcomes = 10 tests, exact McNemar tests on paired cases, Holm correction over the 10; effect size = conditional odds ratio, with the Haldane–Anscombe correction (0.5 added to each discordant cell) when a cell is empty. α = 0.05. All other pairs (B0–B3 included) are reported as exploratory, Holm-corrected among themselves.
- **Factorial effects:** mixed-effects logistic regression with configuration (CAR, SCV and CAR × SCV for B4–B7), model and scenario as fixed effects and random intercepts for case and process. The CAR × SCV term tests H3; configuration × model tests H4.
- **Continuous outcomes** (latency, cost, fitness): Friedman test, Wilcoxon signed-rank post-hoc tests with Holm correction, Cliff's δ, 10,000-resample bootstrap 95 % CIs.
- **Power.** Detecting a 10-point difference in violation rate with ≈ 15 % discordant pairs at power 0.8 requires 197 paired cases at the strictest Holm step (α = 0.05 / 10, two-sided; McNemar, normal approximation); the 196-case sample reaches power 0.80 there and more at every later Holm step. Per-scenario estimates (28 cases each) are descriptive.
- **Stopping rule.** Every registered configuration × model runs on all 196 confirmatory cases with seed 42; no run is stopped or repeated on the basis of its results. Cases are independent, so a run interrupted for technical reasons (model unreachable, machine restarted) resumes at its first case without an outcome; a case whose model could not be reached is not scored but re-run.

## 7. Deviations from the original proposal

| Proposal | This registration | Reason |
|---|---|---|
| BPI Challenge 2019 (purchase-to-pay) | Helpdesk (IT service) | the BPI 2019 log (≈ 700 MB) was unavailable from its repository and exceeds the available memory; Helpdesk is public, light and adds a domain |
| frontier API model + open-weight ≈ 30B + ≈ 8B | gpt-oss-120b + gpt-oss-20b (open-weight, free tier) | no budget for API models; one model family at two sizes keeps the small-vs-large contrast of H4 |
| references = gold adaptations agreed by two annotators | automated references, audited on a 20 % sample | the reference behaviour is derived from the observed continuation and the scenario rules |
| repair hints from a planner (Fast Downward) | the verifier's violation report is the repair feedback | the planner integration is not part of the artifact |
| executor agent | deterministic executor that runs the approved plan | execution is replayed against the benchmark; the executor cannot change an approved plan |
| tune τ, α, β, γ and k on the pilot split | tune τ only | budget; the pilot showed τ to be the setting that matters |
| all evaluation cases, seeds 42–44 | 196-case confirmatory sample, seed 42; seeds 43–44 exploratory | the free tier allows ≈ 13 cases of B4–B7 per model per day; 196 cases are what the power analysis needs |
| default reasoning of the model | reasoning effort *low*, for every configuration | hidden reasoning tripled the tokens per case against the daily quota |

## 8. Artifact

Code, benchmark export and analysis scripts: [repository URL]. Every run records its configuration, seed, the served model version, the verifier report and a hash-chained audit log.
