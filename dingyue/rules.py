"""Local logic: normalise merchants, infer cycle, annualise, renewals, duplicates, cut order."""

import calendar
import json
import os
import re
from datetime import date, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_CACHE = {}

FACTOR = {"月": 12, "季": 4, "半年": 2, "年": 1}
STEP = {"月": 1, "季": 3, "半年": 6, "年": 12}

DATE_RE = re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})|(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|号)")
AMOUNT_RE = re.compile(r"(?:¥|￥|\$)?\s*(\d{1,6}(?:\.\d{1,2})?)\s*(?:元|块|/月|每月)?")
LINE_RE = re.compile(r"^(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\s*)?(.+?)\s*[:：,，]?\s*"
                     r"(?:¥|￥|\$)?\s*(\d{1,6}(?:\.\d{1,2})?)\s*(?:元|块)?\s*(.*)$")


def load(name):
    if name not in _CACHE:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            _CACHE[name] = json.load(f)
    return _CACHE[name]


def merchants():
    return load("merchants.json")["merchants"]


def normalize(name):
    """Return the canonical merchant dict, or None."""
    low = re.sub(r"\s+", " ", (name or "").strip().lower())
    if not low:
        return None
    best = None
    for m in merchants():
        keys = [m["name"].lower()] + [a.lower() for a in m["aliases"]]
        for k in keys:
            if k and (k in low or low in k):
                score = len(k)
                if best is None or score > best[0]:
                    best = (score, m)
    return best[1] if best else None


def parse_date(text, base=None):
    base = base or date.today()
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        if m.group(1):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return date(base.year, int(m.group(4)), int(m.group(5)))
    except ValueError:
        return None


CYCLE_WORDS = [("每年", "年"), ("年费", "年"), ("年度", "年"), ("按年", "年"),
               ("每季", "季"), ("季度", "季"), ("按季", "季"),
               ("半年", "半年"), ("每半年", "半年"),
               ("每月", "月"), ("月费", "月"), ("按月", "月"), ("连续包月", "月")]


def infer_cycle(text, merchant):
    low = text or ""
    for word, cyc in CYCLE_WORDS:
        if word in low:
            return cyc
    if merchant:
        return merchant["cycle"]
    return "月"


def next_renewal(last, cycle):
    """Add one period, clamped to month length (Jan 31 + 1 month → Feb 28)."""
    months = STEP.get(cycle, 1)
    y, m = last.year, last.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(last.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def parse_bill(text, base=None):
    """Parse lines like '2026-10-03 爱奇艺 25 元 连续包月'."""
    base = base or date.today()
    rows = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        head, amount, tail = m.group(1), float(m.group(2)), m.group(3) or ""
        merchant = normalize(head)
        if merchant is None:
            merchant = normalize(tail)
        if merchant is None:
            continue
        last = parse_date(head) or parse_date(line, base) or base
        cycle = infer_cycle(line, merchant)
        rows.append({
            "merchant": merchant["name"],
            "category": merchant["category"],
            "amount": amount,
            "cycle": cycle,
            "last_charge": last.isoformat(),
            "next": next_renewal(last, cycle).isoformat(),
            "annual": round(amount * FACTOR.get(cycle, 12), 2),
            "cancel": merchant["cancel"],
            "refund": merchant["refund"],
        })
    return rows


def consistency(rows):
    """Same merchant charged at different amounts → flag."""
    groups = {}
    for r in rows:
        groups.setdefault(r["merchant"], []).append(r["amount"])
    out = []
    for name, amounts in groups.items():
        uniq = sorted(set(amounts))
        if len(uniq) > 1:
            out.append({"merchant": name, "amounts": uniq})
    return out


def duplicates(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["category"], []).append(r)
    out = []
    for cat, items in groups.items():
        if len(items) > 1:
            out.append({"category": cat, "items": [i["merchant"] for i in items],
                        "annual": round(sum(i["annual"] for i in items), 2)})
    return out


def cost_per_use(row, uses_per_month):
    if not uses_per_month:
        return None
    annual_uses = uses_per_month * 12
    return round(row["annual"] / annual_uses, 2)


def cut_order(rows, uses=None):
    """Worst value first: high annual cost, low usage."""
    uses = uses or {}
    ranked = []
    for r in rows:
        u = uses.get(r["merchant"])
        cpu = cost_per_use(r, u)
        score = r["annual"] if cpu is None else cpu * 100
        ranked.append({**r, "uses": u, "per_use": cpu, "score": round(score, 2)})
    return sorted(ranked, key=lambda x: -x["score"])


def total(rows):
    return round(sum(r["annual"] for r in rows), 2)


def refund_window(row, today=None):
    """Days left in the merchant's refund window, if it can be computed."""
    today = today or date.today()
    days = 7
    if "14 天" in row["refund"]:
        days = 14
    if "5 天" in row["refund"]:
        days = 5
    start = date.fromisoformat(row["last_charge"])
    left = (start + timedelta(days=days) - today).days
    return {"days": days, "left": max(0, left), "open": left >= 0}


def analyze(text, uses=None, base=None):
    rows = parse_bill(text, base)
    return {
        "rows": rows,
        "total": total(rows),
        "count": len(rows),
        "duplicates": duplicates(rows),
        "inconsistent": consistency(rows),
        "cut": cut_order(rows, uses)[:5],
        "refunds": [{"merchant": r["merchant"], **refund_window(r)} for r in rows],
    }
