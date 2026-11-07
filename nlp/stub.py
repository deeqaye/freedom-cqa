"""Keyword-based placeholder evaluator. Satisfies the contract so the service/UI work end-to-end.
Replace by implementing nlp/evaluator.py (see CONTRACT.md)."""
from __future__ import annotations

import re

GREET = re.compile(r"здравствуйте|добр(ый|ое)|привет|сәлем|қайырлы|hello|hi\b|good (morning|afternoon|evening)", re.I)
INTRO = re.compile(r"меня зовут|my name is|менің атым|атым", re.I)
BYE = re.compile(r"до свидания|хорошего|всего доброго|сау болыңыз|goodbye|have a (nice|great|good)|bye", re.I)
RISK = re.compile(r"риск|не гарантир|убыт|тәуекел|risk|not guaranteed", re.I)
INVEST = re.compile(r"акци|облигац|сделк|доходн|инвест|портфел|бирж|stock|bond|trade|invest", re.I)
NEXT = re.compile(r"обращени|заявк|в течение|рабоч(их|ие) дн|срок|свяжемся|ticket|within|business day", re.I)
IDENT = re.compile(r"кодов|подтверд|верификац|идентифик|кодты|растаңыз|verify|verification|confirm your", re.I)


def evaluate(conversation: dict, checklist: dict) -> dict:
    turns = conversation["transcript"]
    op = [t for t in turns if t["speaker"] == "operator"]
    first, last = (op[0], op[-1]) if op else (None, None)
    any_ident = [t for t in op if IDENT.search(t["text"])]
    out = []
    for c in checklist["criteria"]:
        cid, ctype = c["id"], c["type"]
        ev = [first["turn"]] if first else [turns[-1]["turn"]]
        if not op:
            value = None if c.get("na_allowed") else (False if ctype != "scale" else min(c["steps"]))
            rat = "Оператор не подключился к диалогу."
        elif cid == "contact":
            value = bool(GREET.search(first["text"]) and INTRO.search(first["text"]))
            rat = "Приветствие и представление в первой реплике." if value else "В первой реплике нет приветствия или представления."
        elif cid == "closure":
            value = bool(BYE.search(last["text"]))
            ev = [last["turn"]]
            rat = "Оператор попрощался." if value else "В последней реплике оператора нет прощания."
        elif cid == "identification":
            if any_ident:
                value, ev, rat = True, [any_ident[0]["turn"]], "Оператор запросил подтверждение личности."
            else:
                value, rat = (None if c.get("na_allowed") else False), "Запрос не требовал идентификации (stub)."
        elif cid == "risk_disclosure":
            risk = [t for t in op if RISK.search(t["text"])]
            if risk:
                value, ev, rat = True, [risk[0]["turn"]], "Оператор упомянул риски."
            elif any(INVEST.search(t["text"]) for t in turns):
                value, rat = False, "Обсуждались инвестиции, предупреждения о рисках нет."
            else:
                value, rat = (None if c.get("na_allowed") else True), "Инвестиции не обсуждались (stub)."
        elif cid == "next_step":
            nxt = [t for t in op if NEXT.search(t["text"])]
            value = bool(nxt)
            ev = [nxt[0]["turn"]] if nxt else [last["turn"]]
            rat = "Оператор назвал следующий шаг или срок." if value else "Следующий шаг не назван."
        elif ctype == "flag":
            value, rat = False, "Грубых нарушений не найдено (stub)."
        elif ctype == "scale":
            steps = sorted(c["steps"])
            value, rat = steps[-2] if len(steps) > 1 else steps[0], "Заглушка: оценка по умолчанию."
        else:
            value, rat = True, "Заглушка: оценка по умолчанию."
        out.append({"criterion_id": cid, "value": value, "rationale": rat, "evidence_turns": ev,
                    "checked_turns": [op[0]["turn"], op[-1]["turn"]] if op else None,
                    "na_reason": rat if value is None else None})
    return {"criteria": out, "model": {"mode": "local", "name": "keyword-stub"},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}}
