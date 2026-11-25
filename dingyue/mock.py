"""Offline draft: same shape as the model answer, built from local numbers only."""


def advice(base):
    out = []
    for c in base["cut"][:3]:
        if c["per_use"] is not None:
            out.append("%s 年花 %s 元,每月用 %s 次,单次约 %s 元 —— 先看它。"
                       % (c["merchant"], c["annual"], c["uses"], c["per_use"]))
        else:
            out.append("%s 年花 %s 元,还没填使用次数 —— 先补次数再决定砍不砍。"
                       % (c["merchant"], c["annual"]))
    for d in base["duplicates"]:
        out.append("%s 类有 %d 个在付:%s,留一个够用。" % (d["category"], len(d["items"]), "、".join(d["items"])))
    if not out:
        out.append("没有可砍的项:先按类别看年化,占比最高的那个值得再确认一次。")
    return out[:5]


def risks(base):
    out = []
    if base["duplicates"]:
        out.append("有 %d 个类别存在重复订阅,年化合计 %s 元。"
                   % (len(base["duplicates"]), sum(d["annual"] for d in base["duplicates"])))
    if base["inconsistent"]:
        out.append("同一商户出现不同扣费金额,可能有涨价或套餐变更,建议核对。")
    if not base["rows"]:
        out.append("没识别出订阅:确认每行带商户名与金额,或先用 --help 看格式。")
    open_refunds = [r for r in base["refunds"] if r["open"] and r["left"] <= 3]
    if open_refunds:
        out.append("%s 的退款窗口只剩 %d 天,要退趁早。"
                   % (open_refunds[0]["merchant"], open_refunds[0]["left"]))
    return out[:4] or ["没有明显风险,注意连续包月到期前 24 小时才能关。"]


def draft(base):
    return {"summary": "共识别 %d 项订阅,年化 %s 元。" % (base["count"], base["total"]),
            "advice": advice(base), "risks": risks(base)}
