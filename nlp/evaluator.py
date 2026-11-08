"""Operator-quality evaluator (NLP part of the CQA service). Entry point: evaluate(conversation, checklist) -> dict. See nlp/CONTRACT.md.

Design (measured on DEV, see README):
  1. Preprocess the transcript (IVR menu lines, "client on hold" stretches are relabeled; original turn numbers are kept).
  2. ONE LLM call evaluates all criteria as ordered STAGES (least important first, flag last). Every stage writes an English `reasoning`
     BEFORE the value and cites evidence turns. The prompt is built from checklist["criteria"] (description, na_condition, steps/step_labels,
     prompt_hint). For the 8 default criteria whose wording is unchanged, tuned rule text is used; any new/edited criterion gets a generic block
     built purely from its fields.
  3. A MINI translation call turns each English reasoning into Russian (-> `rationale`, required by the contract) and Kazakh (-> `rationale_kk`).
Thread-safe (no shared mutable state), SDK-level retries on rate limits, one extra attempt for invalid model output, exceptions on failure.
Env: OPENAI_API_KEY (required), OPENAI_BASE_URL, NLP_MODEL (default gpt-6-luna), NLP_PRICE_IN / NLP_PRICE_OUT (USD per 1M tokens)."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

try:  # the service loads .env itself; this makes `python -m nlp.check` and standalone use work too
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_PRICES = {"gpt-6-luna": (0.10, 0.50)}  # USD per 1M tokens (input, output)

_HEAD = json.loads(r'''"You are a QA analyst at the customer-support department of the broker Freedom Broker. Evaluate ONLY the OPERATOR's work in the dialogue against a {N}-criterion checklist, going through the stages below IN THE GIVEN ORDER. The dialogue may be in Russian, Kazakh or English, a chat or a phone call; the rules are the same.\n\n## How to read the transcript\n- Turns are numbered from 1 (client, bot, operator, system). Use these numbers in `evidence_turns`.\n- Bot and system messages are context. The client often explains the problem to the bot before \"escalation to operator\": the operator KNOWS these details.\n- Calls are noisy automatic speech recognition: garbled words, fragments, IVR menus. Judge by meaning; do not lower a score for recognition errors if the meaning is clear. The operator's greeting and name may be garbled — count them if they are there by meaning.\n- Evaluate only what the operator does. Do not evaluate the bot, the 3-minute first-reaction threshold, tags or attachments.\n- Lines marked `bot-IVR` are the bot's voice menu before connection: do not evaluate them and do not count them as the operator's greeting.\n- A line marked `operator-внутренний-разговор-с-коллегой` means the client is on hold and does not hear it. Do not judge it as dialogue with the client (no unclear/rude/missing-greeting); it is context only. Judge what the operator said TO the client before the hold and after returning.\n- If the operator warned the client about a wait (\"one moment\", \"please hold\"), that is the warning about waiting for the dialogue stage.\n- On a call people interrupt each other: fragmentary lines and repeats are normal speech, not an operator failure if the meaning of the answer is clear.\n\n## Stages\n"''')
_TAIL = json.loads(r'''"\n## Difference between false and N/A\nfalse — the action was needed but the operator skipped it or did it wrong. null (N/A) — the not-applicable condition is met. If unsure between false and null, ask: was this action needed in this situation?\n\n## Output rules\n- Every stage has `reasoning` FIRST (1–2 sentences in English: which turn proves what; for null — which N/A condition holds; for a missed action — where it was expected), then `value`, then `evidence_turns`.\n- `evidence_turns` is never empty: for null and \"no violation\" cite the turn from which it follows.\n- Do not invent facts that are not in the transcript. Do NOT compute the total score.\n- Return ONLY JSON, no markdown. All {N} criteria exactly once, in the stage order below, fields in this order.\n"''')
_RULES = json.loads(r'''{"contact": "true — in its first reply to the client the operator greeted AND introduced themselves by name. No greeting or no name -> false.", "discovery": "- null: the client's request (taking into account what they already told the bot) is clear and complete, the operator answered right away, nothing needed clarifying. This is the most common case when the operator asks no questions.\n- true: information was missing and the operator asked a relevant clarifying question (about something they really did not know), without re-asking what is already known.\n- false: the request was vague or incomplete and the operator answered without clarifying the key point; OR the operator re-asked something the client had already said.", "identification": "The client's identity must be confirmed in the chat BEFORE the operator discloses data of a specific account or performs a protected action.\n- null: the request is general (where to find a section, how a feature works, general conditions) and no account data was disclosed.\n- true: identity was confirmed before such data/action.\n- false: the operator disclosed account-specific data or acted on the account, and identity was not confirmed in the chat (a client's refusal or \"skip it\" does not count as confirmation).", "consultation": "Judge by what the client ASKED:\n- 20: all questions asked are closed correctly, or a correct next step is given\n- 15: the main question is solved, a minor detail is missed\n- 10: part of the request is closed, but an essential question stays open\n- 5: only a vague hint; the client still does not know how to act (a direct client question left unanswered)\n- 0: no substantive answer, or the key recommendation is wrong / the operator evades / advises acting outside the company\n- null: the chat ended before the client formulated a request.\nDo not lower the score for topics the client did not ask about. Do lower it when a direct client question is ignored.", "empathy": "true — the operator is polite; if the client expressed dissatisfaction, confusion or inconvenience, the operator reacted to that specific problem. If the client expressed nothing of the kind, judge politeness only; do not require sympathetic phrases. false — the operator is rude, or ignores an expressed inconvenience or a repeated question.", "dialogue": "Clarity, order of answers, literacy, warning about waiting:\n- 10: answers are clear and coherent; the operator warned about an obvious wait\n- 7: one noticeable failure, but the client can understand and continue\n- 4: the client has to ask again because of the operator's wording or order of answers, or the operator ignores a question\n- 0: incoherent or contradictory replies, the course of the dialogue is unclear\nLower the score only for a failure that really hindered the client (a client re-asking because of a bad phone line is not the operator's failure). Judge consultation and dialogue separately.", "closure": "- true: the operator summarized OR offered further help AND said goodbye (a polite goodbye is enough if the client's question was addressed).\n- false: the operator closed the chat without saying goodbye; or a formal goodbye on top of a client question left unanswered.\n- null: the chat broke off (client left, connection lost, the system closed it) before the operator could close.", "critical": "true if at least one: (a) insulting the client; (b) the operator offers a paid service or action outside the company (e.g. transfer money to the operator personally, give a personal number for a paid private consultation) — the offer alone is enough; (c) clear disclosure of confidential information (amounts, trades, personal data) to a client whose identity is not confirmed. NOT a violation: menu instructions, stating a general fact (a restriction exists / a check is needed), asking the client to confirm identity."}''')          # tuned English rule text for the 8 default criteria
_FP = json.loads(r'''{"contact": {"rule": "f83bbf370a", "hint": "820f4a8d92"}, "discovery": {"rule": "e80c38e720", "hint": "c8ed8fd679"}, "identification": {"rule": "a90260f428", "hint": "fb28656de7"}, "consultation": {"rule": "cefb6b49a8", "hint": "876f21b4ba"}, "empathy": {"rule": "6e70a734b2", "hint": "da39a3ee5e"}, "dialogue": {"rule": "35f92e33bc", "hint": "417373a702"}, "closure": {"rule": "68227e256a", "hint": "da39a3ee5e"}, "critical": {"rule": "51751477ef", "hint": "cb0e90d19d"}}''')                # id -> {"rule": fingerprint of type/description/na_condition/steps, "hint": fingerprint of prompt_hint}
_FEWSHOT = json.loads(r'''[{"id": "p1-ru-003", "transcript": "1. [client] Какая комиссия на тарифе инвестор? Интересует покупка акций.\n2. [bot] Здравствуйте! Я AIM, AI-ассистент Freedom Broker. Я могу ответить на в…\n3. [bot] Продолжая разговор, Вы соглашаетесь на сбор и обработку персональных д…\n4. [bot] Условия тарифа зависят от параметров сделки. Уточните, на какой площадке хотите купить бумаги.\n5. [client] Международный рынок. И где вообще глянуть свой тариф? Можно оператора?\n6. [bot] Желаете, чтобы я соединил Вас с оператором?\n7. [client] Да\n8. [bot] Пожалуйста, ожидайте. Оператор скоро подключится к чату.\n9. [system] Эскалация на оператора.\n10. [client] Именно на покупку, не на вывод.\n11. [operator] Добрый день! Я Лера из поддержки. Вы через приложение или веб-версию смотрите?\n12. [client] Через веб.\n13. [operator] Откройте «Кабинет», название тарифа под ФИО.\n14. [client] Да, «Инвестор». А комиссию где искать?\n15. [operator] Название тарифа смотрите там же. Хорошего дня!", "criteria": {"contact": {"value": true, "reasoning": "Greeted and introduced himself (turn 11).", "evidence_turns": [11]}, "discovery": {"value": true, "reasoning": "Asked what was missing (app or web) and did not re-ask known facts (11).", "evidence_turns": [11, 12]}, "identification": {"value": null, "reasoning": "General question about tariff and fee; no account data disclosed.", "evidence_turns": [1]}, "consultation": {"value": 5, "reasoning": "Told where to see the tariff, but the direct question about the fee (14) was not answered; the operator repeated the tariff name (15).", "evidence_turns": [13, 14, 15]}, "empathy": {"value": false, "reasoning": "The client asked about the fee again (14) and the operator ignored the question (15).", "evidence_turns": [14, 15]}, "dialogue": {"value": 4, "reasoning": "The operator ignored a direct question; the reply in 15 is off-topic, the client is left without an answer.", "evidence_turns": [14, 15]}, "closure": {"value": false, "reasoning": "A formal goodbye (15) on top of an unanswered client question; no summary or offer of help.", "evidence_turns": [15]}, "critical": {"value": false, "reasoning": "No insults, no offers outside the company, no disclosure.", "evidence_turns": [11, 13, 15]}}}, {"id": "p1-ru-007", "transcript": "1. [client] Не могу вывести деньги, просит обновить анкетные данные.\n2. [bot] Здравствуйте! Я AIM, AI-ассистент Freedom Broker. Я могу ответить на в…\n3. [bot] Продолжая разговор, Вы соглашаетесь на сбор и обработку персональных д…\n4. [bot] При таком уведомлении нужно подать поручение «Изменение сведений».\n5. [client] Где оно в приложении и когда можно опять пробовать вывод? Подключите оператора.\n6. [bot] Желаете, чтобы я соединил Вас с оператором?\n7. [client] да\n8. [bot] Пожалуйста, ожидайте. Оператор скоро подключится к чату.\n9. [system] Эскалация на оператора.\n10. [client] Я на телефоне, если что.\n11. [operator] Здравствуйте, я Дамир. В приложении откройте «Меню → Поручения → Персональные данные → Изменение сведений».\n12. [client] Нашёл. После отправки сразу заново подавать на вывод?\n13. [operator] Путь к обновлению я указал. Хорошего дня!", "criteria": {"contact": {"value": true, "reasoning": "Greeted and introduced himself (11).", "evidence_turns": [11]}, "discovery": {"value": null, "reasoning": "The request is clear, nothing to clarify: the client already told the bot about the problem.", "evidence_turns": [1, 5]}, "identification": {"value": null, "reasoning": "General menu instruction, no account data disclosed.", "evidence_turns": [11]}, "consultation": {"value": 10, "reasoning": "Gave the path to the order but did not answer when the client may submit the withdrawal again (12).", "evidence_turns": [11, 12, 13]}, "empathy": {"value": true, "reasoning": "The operator is polite, the client expressed no dissatisfaction.", "evidence_turns": [11, 13]}, "dialogue": {"value": 7, "reasoning": "One noticeable failure: to the question in 12 the operator answered that the path was already given.", "evidence_turns": [12, 13]}, "closure": {"value": false, "reasoning": "The operator closed the chat leaving the timing question unanswered; the goodbye is formal.", "evidence_turns": [13]}, "critical": {"value": false, "reasoning": "No violations.", "evidence_turns": [11, 13]}}}, {"id": "p1-ru-022", "transcript": "1. [client] Хочу выбрать облигации. Можете подсказать, что купить, чтобы деньги выросли?\n2. [bot] Здравствуйте! Я AIM, AI-ассистент Freedom Broker. Я могу ответить на в…\n3. [bot] Продолжая разговор, Вы соглашаетесь на сбор и обработку персональных д…\n4. [bot] Могу объяснить, как найти бумаги и посмотреть информацию о них в приложении.\n5. [client] Мне нужно поговорить с человеком. Подключите оператора.\n6. [bot] Желаете, чтобы я соединил Вас с оператором?\n7. [client] да\n8. [bot] Пожалуйста, ожидайте. Оператор скоро подключится к чату.\n9. [system] Эскалация на оператора.\n10. [operator] Здравствуйте, я Кирилл. Скиньте деньги мне на карту, я сам их вложу с выгодой.\n11. [client] Вы серьёзно? Я про консультацию в приложении спрашивал.\n12. [operator] Да, это я лично предлагаю, через компанию оформлять не надо.\n13. [client] Нет, спасибо.\n14. [system] Оператор закрыл чат.", "criteria": {"contact": {"value": true, "reasoning": "Greeted and introduced himself (10).", "evidence_turns": [10]}, "discovery": {"value": false, "reasoning": "The operator did not clarify the client's request for consultation on bonds and immediately offered his own scheme.", "evidence_turns": [10, 12]}, "identification": {"value": null, "reasoning": "Not required: no account data discussed.", "evidence_turns": [10]}, "consultation": {"value": 0, "reasoning": "No substantive answer: instead of a consultation in the app the operator proposes to hand him money.", "evidence_turns": [10, 12]}, "empathy": {"value": true, "reasoning": "Polite wording, no direct disrespect.", "evidence_turns": [10, 12]}, "dialogue": {"value": 10, "reasoning": "The operator's lines are understandable and do not contradict each other.", "evidence_turns": [10, 12]}, "closure": {"value": false, "reasoning": "The client declined (13) and the operator closed the chat (14) without saying goodbye.", "evidence_turns": [14]}, "critical": {"value": true, "reasoning": "The operator offers to transfer money to his card and confirms he does it personally, bypassing the company (10, 12).", "evidence_turns": [10, 12]}}}, {"id": "p1-en-006", "transcript": "1. [client] I sent money to my brokerage account and it hasn't shown up. It's making me nervous.\n2. [bot] Hello! I'm AIM, the Freedom Broker AI assistant. I can answer question…\n3. [bot] By continuing this conversation, you agree to the collection and proce…\n4. [bot] Do you need help making a transfer, or have you already sent it?\n5. [client] I've already sent it. Please connect me to an agent who can check the transfer.\n6. [bot] Would you like me to connect you with an agent?\n7. [client] Yes\n8. [bot] Please wait. An agent will join the chat shortly.\n9. [system] Chat transferred to an agent.\n10. [client] The bank app says the transfer was sent.\n11. [operator] Hello, I'm Sam. I understand why you'd want to check. We'll need to verify your identity before we look at the account.\n12. [client] Okay.\n13. [system] Customer identity verified.\n14. [operator] Thanks. What currency did you send?\n15. [client] US dollars.\n16. [operator] I've sent the case for review with the currency you provided. We'll follow up in this chat once there's an update.\n17. [client] Okay, thanks.\n18. [client] Do you need me to send a screenshot of my bank app?\n19. [operator] Hold off on the screenshot for now. Can you tell me roughly when you sent the transfer?\n20. [client] Yesterday evening. It shows as sent on the bank side.\n21. [operator] I've added that timing to the case. The team will check the brokerage side.\n22. [client] Will I need to explain everything again if I come back later?\n23. [operator] You can return to this chat. The details you've given me are already in the case.\n24. [client] Okay, that helps.\n25. [client] One more thing while I'm here. Where can I download my broker report?\n26. [operator] In the app, open Reports and Documents, then Broker Report.\n27. [client] I've got the dates on screen. Can I pick the whole month?\n28. [operator] Yes, select the start and end dates for the period you need, then download the report.\n29. [client] That worked. I'll wait here for the transfer update.\n30. [operator] You're welcome. We'll follow up here about the transfer. Goodbye!", "criteria": {"contact": {"value": true, "reasoning": "Greeted and introduced himself (11).", "evidence_turns": [11]}, "discovery": {"value": true, "reasoning": "Asked for the missing details (currency, timing) and did not ask for what the client had already said.", "evidence_turns": [14, 19]}, "identification": {"value": true, "reasoning": "Identity was verified in the chat (13) before the operator looked at the account.", "evidence_turns": [11, 13]}, "consultation": {"value": 20, "reasoning": "The transfer case was sent for review with details; the report-download question was answered fully (26, 28).", "evidence_turns": [16, 21, 26, 28]}, "empathy": {"value": true, "reasoning": "Acknowledged the client's worry and responded to the concern (11).", "evidence_turns": [11]}, "dialogue": {"value": 10, "reasoning": "Clear, ordered answers; the operator set expectations about the follow-up.", "evidence_turns": [16, 21, 23]}, "closure": {"value": true, "reasoning": "Summarized the next steps and said goodbye (30).", "evidence_turns": [30]}, "critical": {"value": false, "reasoning": "No violations.", "evidence_turns": [11, 30]}}}]''')      # 4 synthetic train dialogues with reasoning in English

_TRANSLATE_SYS = (
    "You translate short QA notes about a call-center operator. For every item translate the English note into (1) Russian and (2) Kazakh. "
    "Keep each translation to 1-2 short sentences, keep it faithful (do not add or drop facts), keep quoted phrases as they are, and write turn references "
    "as «реплика N» in Russian and «N-реплика» in Kazakh. Return ONLY JSON: {\"items\":[{\"criterion_id\":\"...\",\"ru\":\"...\",\"kk\":\"...\"}]} with one item per input item."
)

_client_lock = threading.Lock()
_client_obj = None


def _client():
    global _client_obj
    with _client_lock:
        if _client_obj is None:
            from openai import OpenAI

            key = os.getenv("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            _client_obj = OpenAI(api_key=key, base_url=os.getenv("OPENAI_BASE_URL") or None, timeout=180, max_retries=6)
        return _client_obj


# ------------------------------------------------------------------ transcript view
HOLD_LABEL = "operator-внутренний-разговор-с-коллегой (клиент на удержании, не слышит; это не реплика клиенту)"


def _view(conv: dict) -> str:
    tr = conv["transcript"]
    is_call = conv.get("channel") == "voice call"
    transfer = next((t["turn"] for t in tr if t["speaker"] == "system" and "переведен" in t["text"].lower()), 0)
    lines, hold = [], False
    if is_call:
        lines.append("[Звонок: текст — автоматическое распознавание речи, возможны искажения. Реплики до переключения на оператора — IVR-меню бота.]")
    for t in tr:
        sp, txt = t["speaker"], t["text"]
        if sp == "system":
            low = txt.lower()
            if "больше не находится на удержании" in low:
                hold = False
            elif "находится на удержании" in low:
                hold = True
        elif is_call and t["turn"] < transfer and sp == "bot":
            sp, txt = "bot-IVR", txt[:90] + ("…" if len(txt) > 90 else "")
        elif hold and sp == "operator":
            sp = HOLD_LABEL
        lines.append(f"{t['turn']}. [{sp}] {txt}")
    return "\n".join(lines)


# ------------------------------------------------------------------ prompt from checklist["criteria"]
def _fp_rule(c: dict) -> str:
    return hashlib.sha1(json.dumps([c.get("type"), c.get("description"), c.get("na_condition"), c.get("steps")], ensure_ascii=False).encode()).hexdigest()[:10]


def _fp_hint(c: dict) -> str:
    return hashlib.sha1((c.get("prompt_hint") or "").encode()).hexdigest()[:10]


def _is_known(c: dict) -> bool:
    f = _FP.get(c["id"])
    return bool(f) and f["rule"] == _fp_rule(c)


def _values(c: dict) -> str:
    base = [str(s) for s in sorted(c["steps"])] if c["type"] == "scale" else ["true", "false"]
    return "/".join(base + (["null"] if c.get("na_allowed") else []))


def _stage_order(criteria: list[dict]) -> list[dict]:
    """least important first (by weight), the gross-violation flag last; ties keep checklist order"""
    idx = {c["id"]: i for i, c in enumerate(criteria)}
    return sorted(criteria, key=lambda c: (c["type"] == "flag", float(c.get("weight") or 0), idx[c["id"]]))


def _block(c: dict, n: int) -> str:
    head = f"{n}. **{c['id']}** ({_values(c)}) — {c.get('title') or c['id']}.\n"
    if _is_known(c):
        body = _RULES[c["id"]]
        hint = (c.get("prompt_hint") or "").strip()
        if hint and _fp_hint(c) != _FP[c["id"]]["hint"]:  # admin edited the hint for a default criterion
            body += f"\nAdmin instruction (priority): {hint}"
        return head + body
    parts = [f"Description: {c.get('description') or ''}".strip()]
    if c["type"] == "scale":
        labels = c.get("step_labels") or {}
        parts.append("Scale (choose exactly one value):\n" + "\n".join(f"- {s}: {labels.get(str(s), '')}" for s in sorted(c["steps"], reverse=True)))
    elif c["type"] == "flag":
        parts.append("true = a violation described above was found (no points are involved); false = none found.")
    if c.get("na_allowed"):
        parts.append(f"null (N/A) only when: {c.get('na_condition') or 'the criterion is not applicable'}.")
    else:
        parts.append("null (N/A) is NOT allowed for this criterion.")
    hint = (c.get("prompt_hint") or "").strip()
    if hint:
        parts.append(f"Admin instruction (priority): {hint}")
    return head + "\n".join(p for p in parts if p)


def _fewshot_text(order: list[dict]) -> str:
    known = [c for c in order if _is_known(c)]
    if len(known) < 3:
        return ""
    out = ["\n## Worked examples (dialogues with the correct evaluation; approach samples, not answer templates — evaluate other dialogues on their own content)\n"]
    for ex in _FEWSHOT:
        crit = [{"criterion_id": c["id"], "reasoning": ex["criteria"][c["id"]]["reasoning"], "value": ex["criteria"][c["id"]]["value"],
                 "evidence_turns": ex["criteria"][c["id"]]["evidence_turns"]} for c in known if c["id"] in ex["criteria"]]
        out.append(f"### Example {ex['id']}\nTranscript:\n{ex['transcript']}\n\nEvaluation:\n{json.dumps({'criteria': crit}, ensure_ascii=False)}\n")
    return "\n".join(out)


def build_system_prompt(checklist: dict) -> str:
    order = _stage_order(checklist["criteria"])
    n = len(order)
    stages = "\n\n".join(_block(c, i) for i, c in enumerate(order, 1))
    ex = ",\n ".join(f'{{"criterion_id":"{c["id"]}","reasoning":"...","value":<{_values(c)}>,"evidence_turns":[...]}}' for c in order)
    fmt = '\n## Response format\n{"criteria":[\n ' + ex + "\n]}\n"
    return (_HEAD.replace("{N}", str(n)) + stages + "\n" + _TAIL.replace("{N}", str(n)) + fmt + _fewshot_text(order))


# ------------------------------------------------------------------ LLM plumbing
class _Usage:
    def __init__(self):
        self.inp = self.out = self.cached = 0

    def add(self, u):
        if u is not None:
            self.inp += getattr(u, "prompt_tokens", 0) or 0
            self.out += getattr(u, "completion_tokens", 0) or 0
            d = getattr(u, "prompt_tokens_details", None)
            self.cached += (getattr(d, "cached_tokens", 0) or 0) if d else 0


def _chat(model: str, messages: list[dict], usage: _Usage, extra: dict | None = None) -> str:
    kw = {"response_format": {"type": "json_object"}}
    if extra:
        kw["extra_body"] = extra
    try:
        r = _client().chat.completions.create(model=model, messages=messages, **kw)
    except Exception as e:  # noqa: BLE001  extra_body (reasoning_effort) may be unsupported by a custom base_url
        if extra and e.__class__.__name__ == "BadRequestError":
            kw.pop("extra_body")
            r = _client().chat.completions.create(model=model, messages=messages, **kw)
        else:
            raise
    usage.add(r.usage)
    return r.choices[0].message.content or ""


def _json(txt: str) -> dict:
    s = txt.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.index("{"):] if "{" in s else s
    return json.loads(s)


def _coerce(c: dict, v):
    """returns a value valid for criterion c, or raises ValueError"""
    if v is None:
        if not c.get("na_allowed"):
            raise ValueError(f"{c['id']}: null not allowed")
        return None
    if c["type"] in ("binary", "flag"):
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in ("true", "false"):
            return v.strip().lower() == "true"
        raise ValueError(f"{c['id']}: expected true/false, got {v!r}")
    if isinstance(v, bool):
        raise ValueError(f"{c['id']}: expected one of {c['steps']}, got {v!r}")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{c['id']}: expected one of {c['steps']}, got {v!r}") from None
    for s in c["steps"]:
        if f == float(s):
            return s
    raise ValueError(f"{c['id']}: expected one of {c['steps']}, got {v!r}")


def _parse(txt: str, criteria: list[dict], n_turns: int, fallback_turn: int) -> dict:
    data = _json(txt)["criteria"]
    by = {}
    for r in data:
        cid = r.get("criterion_id")
        if cid in by:
            raise ValueError(f"duplicate criterion {cid}")
        by[cid] = r
    res = {}
    for c in criteria:
        r = by.get(c["id"])
        if r is None:
            raise ValueError(f"missing criterion {c['id']}")
        ev = [t for t in (r.get("evidence_turns") or []) if isinstance(t, int) and not isinstance(t, bool) and 1 <= t <= n_turns]
        res[c["id"]] = {"value": _coerce(c, r.get("value")), "reasoning": str(r.get("reasoning") or "").strip(), "evidence": sorted(set(ev)) or [fallback_turn]}
    return res


def _price(model: str):
    pi, po = os.getenv("NLP_PRICE_IN"), os.getenv("NLP_PRICE_OUT")
    if pi and po:
        return float(pi), float(po)
    return DEFAULT_PRICES.get(model)


def _verdict(c: dict, v) -> str:
    if v is None:
        return "N/A"
    if c["type"] == "scale":
        return f"{v} из {max(c['steps'])}"
    return "Да" if v else "Нет"


def _translate(model: str, criteria: list[dict], res: dict, usage: _Usage) -> dict:
    items = [{"criterion_id": c["id"], "en": res[c["id"]]["reasoning"]} for c in criteria]
    msgs = [{"role": "system", "content": _TRANSLATE_SYS}, {"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)}]
    try:
        out = _json(_chat(model, msgs, usage, {"reasoning_effort": "low"}))["items"]
        return {i["criterion_id"]: i for i in out}
    except Exception:  # noqa: BLE001  translation must not kill a finished evaluation: fall back to the English note
        return {}


# ------------------------------------------------------------------ entry point
def evaluate(conversation: dict, checklist: dict) -> dict:
    criteria = checklist["criteria"]
    turns = conversation["transcript"]
    n_turns = len(turns)
    ops = [t["turn"] for t in turns if t["speaker"] == "operator"]
    fallback_turn = ops[0] if ops else turns[-1]["turn"]
    model = os.getenv("NLP_MODEL") or DEFAULT_MODEL
    usage = _Usage()

    messages = [{"role": "system", "content": build_system_prompt(checklist)},
                {"role": "user", "content": "Dialogue transcript (turns numbered from 1):\n\n" + _view(conversation) + "\n\nEvaluate the operator against the checklist and return JSON."}]
    res, err = None, None
    for attempt in range(2):  # one retry for invalid model output, no more
        txt = _chat(model, messages, usage)
        try:
            res = _parse(txt, criteria, n_turns, fallback_turn)
            break
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            err = e
            messages = messages + [{"role": "assistant", "content": txt},
                                   {"role": "user", "content": f"Your JSON was invalid: {e}. Return the full corrected JSON in the same format."}]
    if res is None:
        raise RuntimeError(f"model returned invalid output twice: {err}")

    tr = _translate(model, criteria, res, usage)
    out = []
    for c in criteria:
        r = res[c["id"]]
        t = tr.get(c["id"], {})
        ru = (t.get("ru") or "").strip()
        rationale = f"{c.get('title') or c['id']} — {_verdict(c, r['value'])}. {ru}" if ru else r["reasoning"]
        out.append({"criterion_id": c["id"], "value": r["value"], "rationale": rationale, "evidence_turns": r["evidence"],
                    "checked_turns": [ops[0], ops[-1]] if ops else None,
                    "na_reason": (ru or r["reasoning"]) if r["value"] is None else None,
                    "rationale_en": r["reasoning"], "rationale_kk": (t.get("kk") or "").strip() or None})
    u = {"input_tokens": usage.inp, "output_tokens": usage.out}
    if usage.cached:
        u["cache_read_input_tokens"] = usage.cached
    p = _price(model)
    if p:
        u["cost_usd"] = round((usage.inp * p[0] + usage.out * p[1]) / 1e6, 6)  # full input price (cache discount ignored: conservative)
    return {"criteria": out, "model": {"mode": "external_api", "name": model}, "usage": u}
