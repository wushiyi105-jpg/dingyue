"""Local logic: normalise merchants, infer cycle, annualise, renewals, duplicates, cut order."""

import calendar
import json
import os
import re
from datetime import date, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_CACHE = {}

FACTOR = {"月": 12, "季": 4, "半年": 2, "年": 1, "一次性": 1}
STEP = {"月": 1, "季": 3, "半年": 6, "年": 12, "一次性": 0}

DATE_RE = re.compile(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*[日号]?"
                     r"|(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
# 金额一律带千分位支持:「¥1,288.00」不能被读成 1
AMT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
CUR_RE = re.compile(r"(?:¥|￥|\$)\s*(" + AMT + r")")
YUAN_RE = re.compile(r"(" + AMT + r")\s*元")
# 「首月 9.9 元，次月起 25 元/月」按常态价年化，首月价只作说明
PROMO_RE = re.compile(r"首月\s*(?:¥|￥)?\s*(" + AMT + r")\s*元?[^0-9]{0,8}?次月起\s*(?:¥|￥)?\s*(" + AMT + r")")
TRIAL_RE = re.compile(r"(\d+)\s*天\s*(?:免费)?试用")
# 兜底:没有币种也没有「元」时,取一个不像容量/天数的数字
BARE_RE = re.compile(r"(?<![\d,.])(\d+(?:\.\d+)?)(?!\s*(?:G|GB|g|天|次|个|件))")


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
# 一次性支出不该按订阅年化 12 倍:30 元钱包充值不是 360 元/年
ONE_OFF_WORDS = ("一次性", "买断", "单次", "钱包充值", "永久版")


def infer_cycle(text, merchant):
    low = text or ""
    for word, cyc in CYCLE_WORDS:
        if word in low:
            return cyc
    for word in ONE_OFF_WORDS:
        if word in low:
            return "一次性"
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
    """Parse one bill per line: '2026-10-03 爱奇艺 25 元 连续包月'。

    先剥日期,再找金额:有币种符号的优先,其次「N 元」,最后才兜底裸数字。
    这样「iCloud+ 200G ¥6.00」不会把 200 当金额,「2026年11月3日」也不会被拆成
    商户「2」+ 金额 26。
    """
    base = base or date.today()
    rows = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rest = line
        last = None
        mdate = DATE_RE.search(rest)
        if mdate:
            last = parse_date(mdate.group(0), base)
            rest = (rest[:mdate.start()] + " " + rest[mdate.end():]).strip()
        amount, flags, matched = None, [], None
        pm = PROMO_RE.search(rest)
        if pm:
            first = float(pm.group(1).replace(",", ""))
            amount = float(pm.group(2).replace(",", ""))
            flags.append("首月 %s 元,按常态 %s 元计" % (_fmt(first), _fmt(amount)))
            matched = pm.group(0)
        else:
            cm = CUR_RE.search(rest)
            ym = YUAN_RE.search(rest)
            if cm:
                amount, matched = float(cm.group(1).replace(",", "")), cm.group(0)
            elif ym:
                amount, matched = float(ym.group(1).replace(",", "")), ym.group(0)
            else:
                bm = BARE_RE.search(rest)
                if bm:
                    amount, matched = float(bm.group(1)), bm.group(1)
        if amount is None:
            continue
        merchant_text = rest.replace(matched, " ", 1) if matched else rest
        merchant = normalize(merchant_text)
        if merchant is None:
            merchant = normalize(line)
        if merchant is None:
            continue
        last = last or parse_date(line, base) or base
        cycle = infer_cycle(line, merchant)
        tm = TRIAL_RE.search(rest)
        if tm and cycle != "一次性":
            flags.append("%s 天免费试用:试用期这笔钱是 0,到期才按常态扣" % tm.group(1))
        rows.append({
            "merchant": merchant["name"],
            "category": merchant["category"],
            "amount": amount,
            "cycle": cycle,
            "last_charge": last.isoformat(),
            "next": None if cycle == "一次性" else next_renewal(last, cycle).isoformat(),
            "annual": round(amount * FACTOR.get(cycle, 12), 2),
            "cancel": merchant["cancel"],
            "refund": merchant["refund"],
            "flags": flags,
        })
    return rows


def _fmt(x):
    return ("%g" % x) if isinstance(x, float) else str(x)


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
    """None = 没填;0 = 明确一次都没用,单次成本算不出来但最该砍。

    HTTP 请求里的次数可能是字符串(前端传 "8"),这里统一转 int,别在除法里炸。
    """
    uses = _int_or_none(uses_per_month)
    if uses is None or uses == 0:
        return None
    annual_uses = uses * 12
    return round(row["annual"] / annual_uses, 2)


def _int_or_none(x):
    if x is None or x == "":
        return None
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def cut_order(rows, uses=None):
    """Worst value first: 明确 0 次的排最前,其余按单次成本(没填次数时按年化)。

    一次性支出不进砍单:那不是订阅,砍不掉,只能记账。
    """
    uses = uses or {}
    ranked = []
    for r in rows:
        if r["cycle"] == "一次性":
            continue
        u = _int_or_none(uses.get(r["merchant"]))
        cpu = cost_per_use(r, u)
        zero_use = u == 0
        score = r["annual"] if cpu is None else cpu * 100
        ranked.append({**r, "uses": u, "per_use": cpu, "zero_use": zero_use,
                       "score": round(score, 2)})
    return sorted(ranked, key=lambda x: (not x["zero_use"], -x["score"]))


def total(rows):
    """年化只算订阅,一次性支出单独列,不能混进「每年要花多少」。"""
    return round(sum(r["annual"] for r in rows if r["cycle"] != "一次性"), 2)


def one_off_total(rows):
    return round(sum(r["annual"] for r in rows if r["cycle"] == "一次性"), 2)


def refund_days(row):
    """从商户退款说明里取窗口天数;写明「不退」的返回 0,不给假希望。"""
    text = (row.get("refund") or "").replace(" ", "")
    cycle = row.get("cycle")
    for clause in re.split(r"[，,;；。]", text):
        if not clause:
            continue
        m = re.search(r"(\d+)\s*天", clause)
        if not m:
            continue
        if "不退" in clause:
            continue
        # 「月付…不退,年付 14 天内可申请」按本行周期取对应那句
        if "年付" in clause and cycle != "年":
            continue
        if "月付" in clause and cycle != "月":
            continue
        return int(m.group(1))
    return 0


def refund_window(row, today=None):
    """Days left in the merchant's refund window; open=False when it is closed."""
    today = today or date.today()
    days = refund_days(row)
    if days == 0:
        return {"days": 0, "left": 0, "open": False,
                "note": "商户写明这笔不可退,别指望退款窗口"}
    start = date.fromisoformat(row["last_charge"])
    left = (start + timedelta(days=days) - today).days
    return {"days": days, "left": max(0, left), "open": left >= 0, "note": ""}


def analyze(text, uses=None, base=None):
    rows = parse_bill(text, base)
    subs = [r for r in rows if r["cycle"] != "一次性"]
    return {
        "rows": rows,
        "total": total(rows),
        "count": len(rows),
        "subscription_count": len(subs),
        "one_off_count": len(rows) - len(subs),
        "one_off_total": one_off_total(rows),
        "duplicates": duplicates(subs),
        "inconsistent": consistency(subs),
        "cut": cut_order(rows, uses)[:5],
        "refunds": [{"merchant": r["merchant"], **refund_window(r)} for r in rows],
        "flags": [{"merchant": r["merchant"], "notes": r["flags"]} for r in rows if r["flags"]],
    }
