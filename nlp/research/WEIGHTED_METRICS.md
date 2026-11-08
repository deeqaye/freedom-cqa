# Weighted metrics (current gold v2)

**Weighted agreement** (0-100): for every dialogue, each criterion gets credit 1 (match) / 0 (mismatch) / partial for the two scales (1 - |diff|/max); credits are weighted by the checklist weights (10/15/20/20/15/15/5) and averaged over 65 dialogues. 100 = identical to the human labels.
**Score MAE**: mean absolute difference between the final 0-100 quality score computed from the model's labels and from the human labels (points).
**$/1000**: cost per 1000 evaluated dialogues at the listed token prices. mean ± sd over repeated identical runs.

| config | runs | weighted agreement | on 5 real calls | final-score MAE | $/1000 | critical TP/FP/FN (avg) | what |
|---|---|---|---|---|---|---|---|
| RU-BASE | 8 (failed calls: 0) | 95.17 ± 0.72 | 79.2 ± 5.9 | 4.77 | 0.96 | 5.0/2.2/0.0 | Russian prompt (v4+few-shot+prep), checklist order |
| EN-orig | 6 (failed calls: 0) | 95.46 ± 0.75 | 80.0 ± 4.4 | 4.50 | 0.93 | 5.0/3.7/0.0 | English prompt, stages in checklist order |
| EN-dep | 6 (failed calls: 0) | 94.64 ± 0.56 | 79.2 ± 3.6 | 5.06 | 0.95 | 5.0/3.2/0.0 | English, stages by dependency order (critical first, closure last) |
| EN-dep+brief | 6 (failed calls: 0) | 95.34 ± 0.40 | 81.5 ± 4.6 | 4.64 | 1.03 | 5.0/2.2/0.0 | English, dependency order + case_brief stage 0 |
| EN-wasc | 6 (failed calls: 0) | 95.53 ± 0.53 | 80.1 ± 4.0 | 4.34 | 0.93 | 5.0/2.5/0.0 | English, stages from least to most important (BASE for the 3 hypotheses below) |
| EN-wasc+effort=low | 6 (failed calls: 1) | 95.19 ± 0.60 | 80.8 ± 5.2 | 4.85 | 0.79 | 5.0/3.0/0.0 | hypothesis 1: reasoning_effort=low |
| EN-wasc+no reasoning | 6 (failed calls: 0) | 95.08 ± 0.66 | 77.7 ± 3.9 | 4.68 | 0.93 | 5.0/2.5/0.0 | hypothesis 2: no reasoning field |
| EN-wasc+3 failure examples | 6 (failed calls: 0) | 95.21 ± 0.34 | 77.5 ± 3.3 | 4.59 | 0.95 | 5.0/3.2/0.0 | hypothesis 3: few-shot = 3 failure-heavy examples |

## Where the points are lost (points out of 100, lower is better; weight x error share)

| config | contact (w10) | discovery (w15) | identification (w20) | consultation (w20) | empathy (w15) | dialogue (w15) | closure (w5) | total lost |
|---|---|---|---|---|---|---|---|---|
| RU-BASE | 0.15 | 1.01 | 0.58 | 1.14 | 0.72 | 0.77 | 0.45 | 4.83 |
| EN-orig | 0.15 | 0.77 | 0.51 | 0.74 | 1.00 | 0.99 | 0.37 | 4.54 |
| EN-dep | 0.15 | 1.12 | 0.62 | 1.19 | 0.81 | 0.96 | 0.51 | 5.36 |
| EN-dep+brief | 0.15 | 1.04 | 0.51 | 0.96 | 0.69 | 0.89 | 0.41 | 4.66 |
| EN-wasc | 0.15 | 0.88 | 0.62 | 0.68 | 0.77 | 0.92 | 0.45 | 4.47 |
| EN-wasc+effort=low | 0.15 | 0.92 | 0.36 | 1.18 | 0.85 | 0.91 | 0.44 | 4.81 |
| EN-wasc+no reasoning | 0.15 | 1.00 | 0.56 | 0.81 | 0.92 | 1.00 | 0.47 | 4.92 |
| EN-wasc+3 failure examples | 0.15 | 0.85 | 0.67 | 0.95 | 0.73 | 1.04 | 0.40 | 4.79 |

## Per-criterion agreement (%, mean over runs)

| config | contact | discovery | identification | consultation | empathy | dialogue | closure | critical |
|---|---|---|---|---|---|---|---|---|
| RU-BASE | 98.5 | 93.3 | 97.1 | 94.3 | 95.2 | 94.9 | 91.0 | 96.5 |
| EN-orig | 98.5 | 94.9 | 97.4 | 96.3 | 93.3 | 93.4 | 92.6 | 94.4 |
| EN-dep | 98.5 | 92.6 | 96.9 | 94.0 | 94.6 | 93.6 | 89.7 | 95.1 |
| EN-dep+brief | 98.5 | 93.1 | 97.4 | 95.2 | 95.4 | 94.1 | 91.8 | 96.7 |
| EN-wasc | 98.5 | 94.1 | 96.9 | 96.6 | 94.9 | 93.9 | 91.0 | 96.2 |
| EN-wasc+effort=low | 98.5 | 93.8 | 98.2 | 94.1 | 94.4 | 93.9 | 91.3 | 95.1 |
| EN-wasc+no reasoning | 98.5 | 93.3 | 97.2 | 96.0 | 93.8 | 93.4 | 90.5 | 96.2 |
| EN-wasc+3 failure examples | 98.5 | 94.4 | 96.7 | 95.3 | 95.1 | 93.1 | 92.1 | 95.1 |