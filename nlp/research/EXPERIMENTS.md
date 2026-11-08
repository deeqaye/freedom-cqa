# Experiments on Luna (gpt-6-luna)

Metric: weighted agreement with human gold (0-100). `all`=65 DEV dialogues; `train`=45 synthetic (tuning); `synval`=15 synthetic held-out topics; `real`=5 real calls (very noisy, n=5). Cost = $ per 1000 evaluations. crit = TP/FP/FN of critical.

**Noise floor (BASE prompt x10 identical runs):** all 89.83 ± 0.65 (min 88.45, max 90.88); synval 94.03 ± 0.53; real 70.6 ± 3.8 (min 64.5, max 77.6). Differences below ~±1.3 on `all` (2 sd) between single runs are NOT distinguishable from noise.

## A. 35 prompt hypotheses (single run each, sorted by `all`)

| id | all | train | synval | real | $/1000 | crit | idea |
|---|---|---|---|---|---|---|---|
| P07 | 91.18 | 91.86 | 94.70 | 74.5 | 0.96 | 5/2/1 | Russian speaker labels (Клиент/Бот/Оператор) instead of English tags |
| P02 | 90.87 | 91.62 | 94.70 | 72.6 | 0.92 | 5/3/1 | Value first, reasoning after (rationale instead of chain-of-thought) |
| P31 | 90.81 | 92.08 | 94.07 | 69.6 | 0.84 | 5/1/1 | Model setting: reasoning_effort=low |
| P12 | 90.73 | 92.08 | 93.40 | 70.6 | 1.03 | 5/5/1 | Per-criterion yes/no sub-question checklist to answer inside reasoning |
| P22 | 90.65 | 91.11 | 94.70 | 74.4 | 0.90 | 5/4/1 | Few-shot = only the three failure-heavy chats (no clean positive example) |
| P01 | 90.58 | 91.30 | 94.07 | 73.6 | 0.72 | 5/1/1 | No reasoning field: value + evidence only (cheaper; does reasoning help accuracy at a |
| P35 | 90.51 | 91.53 | 93.73 | 71.6 | 0.97 | 5/2/1 | Tell the model the weights (errors on heavier criteria cost more) |
| P32 | 90.50 | 90.53 | 94.70 | 77.6 | 1.11 | 5/2/1 | Model setting: reasoning_effort=high |
| P23 | 90.43 | 91.10 | 94.10 | 73.4 | 0.97 | 5/4/1 | Examples moved from system into the user message, before the transcript |
| P17 | 90.36 | 90.67 | 94.07 | 76.5 | 0.96 | 5/2/1 | critical needs a verbatim quote of the violating utterance, else false |
| P13 | 90.25 | 90.40 | 94.07 | 77.5 | 0.96 | 5/2/1 | Concrete anchor examples for each step of the two scales |
| P15 | 90.21 | 90.68 | 94.70 | 72.5 | 1.03 | 5/2/1 | Explicit applicability gate: 'applicable' field decided BEFORE value (null iff not ap |
| P04 | 90.20 | 90.54 | 93.77 | 76.4 | 1.02 | 5/2/1 | Reasoning must contain a short exact quote from the cited turn |
| P14 | 90.19 | 90.54 | 94.70 | 73.5 | 0.98 | 5/3/1 | Base-rate hint computed from TRAIN gold (typical frequency of each value) |
| P18 | 90.09 | 90.94 | 94.07 | 70.5 | 0.98 | 5/2/1 | Strict empathy gate: false only if client expressed negative emotion AND operator ign |
| P05 | 89.98 | 90.88 | 93.73 | 70.6 | 0.94 | 5/2/1 | Operator-centric view: bot lines dropped, client pre-escalation statements shown as ' |
| P28 | 89.98 | 90.88 | 93.73 | 70.7 | 1.01 | 5/1/1 | Contrastive reasoning for scales: state what prevented the next higher step |
| P26 | 89.95 | 90.63 | 93.40 | 73.4 | 0.98 | 5/3/1 | Persona: supportive coach who credits intent |
| P19 | 89.86 | 89.49 | 94.70 | 78.7 | 0.71 | 5/0/1 | Zero-shot (v4 rules only, no examples) |
| P03 | 89.82 | 90.43 | 94.40 | 70.5 | 1.00 | 5/1/1 | Dialogue summary field before criteria (global understanding first) |
| P10 | 89.81 | 90.63 | 94.07 | 69.6 | 0.97 | 5/1/1 | Optimistic default: start from the top score, lower only with explicit evidence |
| P25 | 89.75 | 91.33 | 93.40 | 64.6 | 0.98 | 5/4/1 | Persona: strict external auditor |
| P30 | 89.75 | 89.98 | 94.07 | 74.7 | 0.91 | 5/2/1 | Reasoning written in English (token efficiency / model strength) while rubric stays R |
| BASE | 89.72 | 90.53 | 94.70 | 67.5 | 0.96 | 5/3/1 | baseline: v4 + few-shot + prep |
| P16 | 89.72 | 90.41 | 94.70 | 68.5 | 0.99 | 5/2/1 | Conservative N/A: null only when the N/A condition is literally met |
| P29 | 89.72 | 90.41 | 94.70 | 68.6 | 2.00 | 5/1/1 | Two-pass self-critique (answer, then audit and fix its own JSON) |
| P09 | 89.45 | 90.77 | 92.43 | 68.7 | 1.02 | 5/4/1 | Strict JSON schema (structured outputs) with enum-constrained values |
| P11 | 89.35 | 90.56 | 94.37 | 63.4 | 0.98 | 5/3/1 | Pessimistic default: hunt for defects, no top score without checking every sub-condit |
| P27 | 89.30 | 89.68 | 94.07 | 71.6 | 1.03 | 5/2/1 | Timeline first: list operator actions per turn before judging |
| P06 | 89.12 | 89.41 | 94.10 | 71.6 | 0.96 | 5/2/1 | Drop bot boilerplate (greeting/consent text) to cut noise |
| P08 | 88.98 | 90.28 | 92.23 | 67.5 | 1.15 | 5/4/1 | Include relative timestamps per line (lets model see waiting/latency) |
| P33 | 88.91 | 89.77 | 94.07 | 65.7 | 0.83 | 5/5/1 | Rubric restructured as one compact table (+ few-shot kept) |
| P21 | 88.90 | 89.78 | 94.07 | 65.5 | 0.89 | 5/3/1 | Few-shot with values only (no reasoning) — compact examples |
| P20 | 88.64 | 88.82 | 93.40 | 72.7 | 0.85 | 5/2/1 | Two few-shot examples only (cheaper) |
| P24 | 88.18 | 89.06 | 93.73 | 63.7 | 0.97 | 5/0/1 | Examples as real multi-turn chat (user=transcript, assistant=JSON) |
| P34 | 86.24 | 87.56 | 91.43 | 58.8 | 0.65 | 5/4/1 | Minimal prompt: compact table rubric, ONE example (max cost saving) |

## B. 35 feature-pipeline variants (7 extractors x 5 scorers; R=rules, T=decision tree fit on train, L=LLM on facts, LT=LLM on facts+transcript, H=rules for yes/no + LLM for scales)

| id | all | train | synval | real | $/1000 | crit | idea |
|---|---|---|---|---|---|---|---|
| E5-LT | 86.83 | 87.87 | 91.40 | 63.8 | 1.54 | 5/2/1 | one worked example of facts in the prompt ; scorer LT |
| E0-LT | 86.68 | 88.62 | 90.50 | 57.7 | 1.48 | 5/1/1 | base schema, prepped transcript ; scorer LT |
| E5-H | 86.29 | 87.20 | 89.40 | 68.8 | 1.54 | 5/2/1 | one worked example of facts in the prompt ; scorer H |
| E5-L | 85.93 | 87.30 | 89.50 | 62.9 | 1.48 | 5/3/1 | one worked example of facts in the prompt ; scorer L |
| E4-LT | 85.76 | 87.41 | 89.80 | 58.8 | 1.42 | 5/2/1 | compact style (short summaries) ; scorer LT |
| E3-LT | 85.51 | 87.78 | 88.90 | 54.9 | 1.58 | 5/2/1 | two focused calls: operator-behavior facts + client-request facts, merged ; scorer LT |
| E0-L | 85.47 | 87.51 | 89.53 | 54.9 | 1.40 | 5/2/1 | base schema, prepped transcript ; scorer L |
| E6-LT | 85.47 | 86.80 | 89.70 | 60.8 | 1.76 | 5/3/1 | reasoning_effort=high ; scorer LT |
| E5-R | 85.37 | 86.54 | 88.80 | 64.5 | 0.81 | 5/2/1 | one worked example of facts in the prompt ; scorer R |
| E6-T | 85.36 | 85.31 | 89.43 | 73.6 | 1.06 | 1/0/5 | reasoning_effort=high ; scorer T |
| E0-H | 85.29 | 87.51 | 87.50 | 58.7 | 1.48 | 5/1/1 | base schema, prepped transcript ; scorer H |
| E2-T | 85.23 | 84.61 | 89.10 | 79.2 | 0.91 | 1/0/5 | evidence quote required for each fact ; scorer T |
| E6-L | 85.23 | 86.47 | 88.73 | 63.6 | 1.73 | 5/3/1 | reasoning_effort=high ; scorer L |
| E1-T | 85.22 | 86.22 | 84.10 | 79.5 | 0.76 | 1/0/5 | raw transcript (no IVR/hold preprocessing) ; scorer T |
| E3-T | 85.15 | 84.89 | 87.77 | 79.7 | 0.84 | 1/0/5 | two focused calls: operator-behavior facts + client-request facts, merged ; scorer T |
| E4-H | 84.99 | 86.08 | 88.80 | 63.8 | 1.42 | 5/2/1 | compact style (short summaries) ; scorer H |
| E4-T | 84.95 | 85.87 | 87.70 | 68.4 | 0.67 | 1/0/5 | compact style (short summaries) ; scorer T |
| E6-H | 84.93 | 86.13 | 88.70 | 62.8 | 1.76 | 5/3/1 | reasoning_effort=high ; scorer H |
| E1-LT | 84.84 | 86.29 | 89.80 | 56.9 | 1.47 | 5/3/1 | raw transcript (no IVR/hold preprocessing) ; scorer LT |
| E0-T | 84.82 | 84.57 | 87.10 | 80.3 | 0.74 | 1/0/5 | base schema, prepped transcript ; scorer T |
| E1-H | 84.53 | 85.62 | 88.80 | 61.9 | 1.47 | 5/3/1 | raw transcript (no IVR/hold preprocessing) ; scorer H |
| E3-H | 84.51 | 86.44 | 86.90 | 59.9 | 1.58 | 5/2/1 | two focused calls: operator-behavior facts + client-request facts, merged ; scorer H |
| E2-LT | 84.13 | 84.96 | 89.77 | 59.8 | 1.67 | 5/2/1 | evidence quote required for each fact ; scorer LT |
| E5-T | 84.06 | 82.71 | 90.70 | 76.3 | 0.81 | 1/0/5 | one worked example of facts in the prompt ; scorer T |
| E0-R | 83.85 | 85.66 | 86.90 | 58.5 | 0.74 | 5/1/1 | base schema, prepped transcript ; scorer R |
| E4-L | 83.78 | 85.42 | 88.13 | 55.9 | 1.34 | 5/3/1 | compact style (short summaries) ; scorer L |
| E4-R | 83.72 | 84.84 | 88.50 | 59.3 | 0.67 | 5/2/1 | compact style (short summaries) ; scorer R |
| E3-L | 83.62 | 86.48 | 86.63 | 48.8 | 1.53 | 5/3/1 | two focused calls: operator-behavior facts + client-request facts, merged ; scorer L |
| E6-R | 83.58 | 84.61 | 87.47 | 62.7 | 1.06 | 5/3/1 | reasoning_effort=high ; scorer R |
| E2-H | 83.52 | 84.29 | 88.77 | 60.8 | 1.67 | 5/2/1 | evidence quote required for each fact ; scorer H |
| E1-R | 83.35 | 84.17 | 88.20 | 61.5 | 0.76 | 5/3/1 | raw transcript (no IVR/hold preprocessing) ; scorer R |
| E1-L | 83.23 | 84.53 | 87.83 | 57.7 | 1.42 | 5/3/1 | raw transcript (no IVR/hold preprocessing) ; scorer L |
| E2-L | 82.86 | 83.67 | 89.17 | 56.7 | 1.61 | 5/2/1 | evidence quote required for each fact ; scorer L |
| E3-R | 82.46 | 84.61 | 85.07 | 55.3 | 0.84 | 5/2/1 | two focused calls: operator-behavior facts + client-request facts, merged ; scorer R |
| E2-R | 81.73 | 82.69 | 87.27 | 56.5 | 0.91 | 5/2/1 | evidence quote required for each fact ; scorer R |

## C. Two separate hypotheses, repeated runs (mean ± sd)

| pipeline | n runs | all | train | synval | real | $/1000 |
|---|---|---|---|---|---|---|
| control: BASE prompt | 10 | 89.83 ± 0.65 | 90.56 ± 0.68 | 94.03 ± 0.53 | 70.61 ± 3.79 | 0.96 |
| HP: 8 decomposed single-criterion calls | 20 | 87.28 ± 0.55 | 88.17 ± 0.66 | 93.00 ± 0.64 | 62.09 ± 3.58 | 1.66 |
| control: best feature variant by train (E5+LT, fresh extraction each run) | 10 | 85.31 ± 0.83 | 86.79 ± 1.24 | 89.86 ± 1.30 | 58.25 ± 4.22 | 1.56 |
| HF: per-turn tagging -> code facts -> rules | 20 | 72.01 ± 0.92 | 71.54 ± 0.98 | 79.39 ± 1.26 | 54.08 ± 4.69 | 0.54 |
| re-check P07 (Russian labels) | 5 | 90.25 ± 0.28 | 91.00 ± 0.26 | 94.31 ± 0.48 | 71.34 ± 2.48 | 0.96 |
| re-check P02 (value before reasoning) | 5 | 89.72 ± 0.70 | 90.44 ± 0.70 | 94.19 ± 0.26 | 69.78 ± 4.61 | 0.92 |
| re-check P02+P07 | 5 | 89.90 ± 0.58 | 90.69 ± 0.73 | 94.20 ± 0.33 | 69.96 ± 3.17 | 0.93 |

## D. Per-criterion agreement (mean over repeats)

| pipeline | contact | discovery | identification | consultation | empathy | dialogue | closure | critical |
|---|---|---|---|---|---|---|---|---|
| BASE | 94 | 76 | 93 | 92 | 91 | 92 | 88 | 96 |
| HP | 94 | 72 | 93 | 88 | 86 | 90 | 91 | 98 |
| FEAT_E5_LT | 94 | 70 | 91 | 87 | 85 | 88 | 83 | 95 |
| HF | 95 | 61 | 88 | 49 | 70 | 84 | 57 | 94 |
| PV_P07 | 94 | 76 | 93 | 93 | 93 | 93 | 86 | 94 |