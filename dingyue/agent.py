"""Orchestration: local ledger first, model only for advice wording."""

import json
import re

from . import llm, mock, rules

MONEY_RE = re.compile(r"(?:¥|￥|\$)?\d+(?:\.\d+)?\s*(?:元|块|/月|每月|一年|每年)")


def strip_money(text):
    return MONEY_RE.sub("该金额", text or "")


PROMPT = """你是订阅账单顾问。下面是程序已经算好的台账、年化、重复项和砍单排序,你只负责解释:
- 用 3 句以内说清这一年花在哪些类别上
- 给砍单建议(顺序只能引用下面给的顺序,不要自己重排)
- 指出 2 条风险
- 不要写具体金额,金额由程序统一渲染

只输出 JSON:
{"summary": "...", "advice": ["..."], "risks": ["..."]}

台账:
%s
"""


def analyze(text, uses=None, force_mock=False, config=None):
    base = rules.analyze(text, uses)
    cfg = {**llm.default_config(), **(config or {})}
    if force_mock or not cfg.get("api_key"):
        draft = mock.draft(base)
        mode = "offline"
    else:
        try:
            payload = json.dumps({
                "count": base["count"],
                "subscription_count": base.get("subscription_count", base["count"]),
                "one_off_count": base.get("one_off_count", 0),
                "one_off_total": base.get("one_off_total", 0),
                "total": base["total"],
                "rows": [{k: r[k] for k in ("merchant", "category", "cycle", "annual", "next", "flags")}
                         for r in base["rows"]],
                "duplicates": base["duplicates"],
                "no_refund": [r["merchant"] for r in base["refunds"] if not r["open"] and r["days"] == 0],
                "cut": [{"merchant": c["merchant"], "annual": c["annual"], "per_use": c["per_use"],
                         "uses": c["uses"]} for c in base["cut"]],
            }, ensure_ascii=False, indent=2)
            raw = llm.chat([{"role": "user", "content": PROMPT % payload}], config=cfg)
            draft = llm.extract_json(raw)
            mode = "model"
        except Exception as e:
            draft = mock.draft(base)
            draft["error"] = str(e)
            mode = "offline"
    def clean(x):
        return strip_money(x) if mode == "model" else (x or "")
    base["summary"] = clean(draft.get("summary"))
    base["advice"] = [clean(x) for x in (draft.get("advice") or []) if str(x).strip()][:5] \
        or mock.advice(base)
    base["risks"] = [clean(x) for x in (draft.get("risks") or [])][:4] or mock.risks(base)
    base["mode"] = mode
    return base
