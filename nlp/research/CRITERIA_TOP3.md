# Топ-3 гипотезы по каждому критерию (на утверждённой разметке)

Пул: 73 гипотез (промпт-варианты, фич-пайплайны, по одному прогону HP/HF). Значение — среднее совпадение с разметкой по критерию, 0–100 (для шкал частичный зачёт). Ранжирование по всем 65; train и val (15 синтетика held-out + 5 звонков) показаны отдельно, чтобы видеть, держится ли лидер. Стоимость — $ за 1000 оценок.

**Шум:** базовый промпт, 8 одинаковых прогонов: contact 98.5±0.0, discovery 93.3±1.7, identification 97.1±1.2, consultation 94.3±1.2, empathy 95.2±1.8, dialogue 94.9±1.1, closure 91.0±1.8, critical 96.5±1.5; взвешенное 95.17±0.72. Разницу меньше 2 sd внутри критерия считать шумом.

## contact (вес 10) — база: 98.5 ± 0.0 (среднее 98.5)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P34 | 98.5 | 100.0 | 95.0 | 0.65 | Minimal prompt: compact table rubric, ONE example (max cost saving) |
| 2 | E4-R | 98.5 | 100.0 | 95.0 | 0.67 | FEAT compact style (short summaries) ; scorer R |
| 3 | P19 | 98.5 | 100.0 | 95.0 | 0.71 | Zero-shot (v4 rules only, no examples) |

## discovery (вес 15) — база: 92.3 ± 1.7 (среднее 93.3)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P20 | 96.9 | 97.8 | 95.0 | 0.85 | Two few-shot examples only (cheaper) |
| 2 | P17 | 96.9 | 97.8 | 95.0 | 0.96 | critical needs a verbatim quote of the violating utterance, else false |
| 3 | P33 | 95.4 | 95.6 | 95.0 | 0.83 | Rubric restructured as one compact table (+ few-shot kept) |

## identification (вес 20) — база: 96.9 ± 1.2 (среднее 97.1)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P19 | 100.0 | 100.0 | 100.0 | 0.71 | Zero-shot (v4 rules only, no examples) |
| 2 | P01 | 100.0 | 100.0 | 100.0 | 0.72 | No reasoning field: value + evidence only (cheaper; does reasoning help acc |
| 3 | P31 | 98.5 | 100.0 | 95.0 | 0.84 | Model setting: reasoning_effort=low |

## consultation (вес 20) — база: 93.8 ± 1.2 (среднее 94.3)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P31 | 96.5 | 96.7 | 96.2 | 0.84 | Model setting: reasoning_effort=low |
| 2 | P22 | 96.2 | 95.0 | 98.8 | 0.90 | Few-shot = only the three failure-heavy chats (no clean positive example) |
| 3 | P03 | 96.2 | 95.0 | 98.8 | 1.00 | Dialogue summary field before criteria (global understanding first) |

## empathy (вес 15) — база: 95.4 ± 1.8 (среднее 95.2)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P01 | 96.9 | 97.8 | 95.0 | 0.72 | No reasoning field: value + evidence only (cheaper; does reasoning help acc |
| 2 | P31 | 96.9 | 97.8 | 95.0 | 0.84 | Model setting: reasoning_effort=low |
| 3 | P21 | 96.9 | 95.6 | 100.0 | 0.89 | Few-shot with values only (no reasoning) — compact examples |

## dialogue (вес 15) — база: 95.8 ± 1.1 (среднее 94.9)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P02 | 96.3 | 98.0 | 92.5 | 0.92 | Value first, reasoning after (rationale instead of chain-of-thought) |
| 2 | P07 | 96.3 | 97.3 | 94.0 | 0.96 | Russian speaker labels (Клиент/Бот/Оператор) instead of English tags |
| 3 | P26 | 96.3 | 97.3 | 94.0 | 0.98 | Persona: supportive coach who credits intent |

## closure (вес 5) — база: 89.2 ± 1.8 (среднее 91.0)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P01 | 98.5 | 97.8 | 100.0 | 0.72 | No reasoning field: value + evidence only (cheaper; does reasoning help acc |
| 2 | P30 | 96.9 | 95.6 | 100.0 | 0.91 | Reasoning written in English (token efficiency / model strength) while rubr |
| 3 | P07 | 96.9 | 95.6 | 100.0 | 0.96 | Russian speaker labels (Клиент/Бот/Оператор) instead of English tags |

## critical (вес —) — база: 95.4 ± 1.5 (среднее 96.5)

| # | гипотеза | all | train | val | $/1000 | идея |
|---|---|---|---|---|---|---|
| 1 | P19 | 100.0 | 100.0 | 100.0 | 0.71 | Zero-shot (v4 rules only, no examples) |
| 2 | P24 | 100.0 | 100.0 | 100.0 | 0.97 | Examples as real multi-turn chat (user=transcript, assistant=JSON) |
| 3 | P01 | 98.5 | 97.8 | 100.0 | 0.72 | No reasoning field: value + evidence only (cheaper; does reasoning help acc |

## Взвешенное совпадение (целевая метрика), топ-5

| гипотеза | wa | $/1000 | critical TP/FP/FN | идея |
|---|---|---|---|---|
| P31 | 96.54 | 0.84 | 5/1/0 | Model setting: reasoning_effort=low |
| P07 | 96.45 | 0.96 | 5/2/0 | Russian speaker labels (Клиент/Бот/Оператор) instead of English tags |
| P01 | 96.31 | 0.72 | 5/1/0 | No reasoning field: value + evidence only (cheaper; does reasoning hel |
| P22 | 95.92 | 0.90 | 5/4/0 | Few-shot = only the three failure-heavy chats (no clean positive examp |
| P32 | 95.77 | 1.11 | 5/2/0 | Model setting: reasoning_effort=high |
| BASE x8 (среднее) | 95.17 ± 0.72 | | | контроль |
| P07 x8 (среднее) | 95.13 ± 0.82 | | | русские метки спикеров |