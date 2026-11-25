"""命令行入口:python -m dingyue <命令>。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, db, llm, rules
from .llm import LLMError

BANNER = ("⚠️  当前为离线模式(未配置 LLM_API_KEY):归一年化、续费日、重复检测、砍单排序全在本地。\n"
          "   填入 LLM_API_KEY 后,摘要与砍单理由由模型撰写(金额仍以本地台账为准)。\n")


def _text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def _uses(args):
    out = {}
    for pair in args.uses or []:
        if ":" in pair:
            name, n = pair.rsplit(":", 1)
            try:
                out[name.strip()] = int(n)
            except ValueError:
                continue
    return out


def render(r):
    mode = "模型" if r["mode"] == "model" else "离线模式"
    lines = ["💳 订阅台账  [%s]" % mode, "",
             "共 %d 项,年化 %s 元(约每月 %s 元)"
             % (r["count"], r["total"], round(r["total"] / 12, 2) if r["count"] else 0), ""]
    lines.append("| # | 商户 | 类别 | 金额 | 周期 | 年化 | 下次续费 |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, x in enumerate(r["rows"], 1):
        lines.append("| %d | %s | %s | %s | %s | %s | %s |"
                     % (i, x["merchant"], x["category"], x["amount"], x["cycle"], x["annual"], x["next"]))
    if not r["rows"]:
        lines.append("| — | 未识别 | — | — | — | — | — |")
    lines.append("")
    if r["duplicates"]:
        lines.append("🔁 重复订阅")
        for d in r["duplicates"]:
            lines.append("  · %s 类:%s(年化 %s 元)" % (d["category"], "、".join(d["items"]), d["annual"]))
        lines.append("")
    if r["inconsistent"]:
        lines.append("⚠️ 金额不一致")
        for c in r["inconsistent"]:
            lines.append("  · %s:%s" % (c["merchant"], " / ".join(str(a) for a in c["amounts"])))
        lines.append("")
    lines.append("✂️ 砍单顺序")
    for i, c in enumerate(r["cut"], 1):
        cpu = ("单次 %.2f 元" % c["per_use"]) if c["per_use"] is not None else "未填使用次数"
        lines.append("  %d. %s —— 年化 %s,月用 %s 次,%s"
                     % (i, c["merchant"], c["annual"], c["uses"] if c["uses"] else "—", cpu))
        lines.append("     取消:%s" % c["cancel"])
    if not r["cut"]:
        lines.append("  · 无")
    lines.append("")
    refunds = [x for x in r["refunds"] if x["open"]]
    if refunds:
        lines.append("↩️ 退款窗口")
        for x in refunds:
            lines.append("  · %s:购买后 %d 天,还剩 %d 天" % (x["merchant"], x["days"], x["left"]))
        lines.append("")
    lines.append("🧭 判断")
    lines.append("  " + (r["summary"] or "—"))
    for a in r["advice"]:
        lines.append("  · " + a)
    if r["risks"]:
        lines.append("")
        lines.append("🚩 风险")
        for x in r["risks"]:
            lines.append("  · " + x)
    return "\n".join(lines)


def cmd_scan(args):
    text = _text(args)
    if not text.strip():
        print("❌ 没有账单内容:每行「日期 商户 金额 [周期]」。", file=sys.stderr)
        sys.exit(2)
    db.use(args.db)
    r = agent.analyze(text, _uses(args), force_mock=args.mock)
    if args.save:
        r["saved_id"] = db.save(r)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(render(r))


def cmd_merchant(args):
    m = rules.normalize(args.name)
    if not m:
        print("❌ 商户表里没有「%s」" % args.name)
        return
    print("%s(%s)" % (m["name"], m["category"]))
    print("  默认周期:%s · 参考价位:%s 元" % (m["cycle"], m["typical_price"]))
    print("  取消路径:" + m["cancel"])
    print("  退款参考:" + m["refund"])


def cmd_next(args):
    rows = rules.parse_bill(_text(args))
    if not rows:
        print("没有识别到订阅。")
        return
    print("📅 续费日历")
    for r in sorted(rows, key=lambda x: x["next"]):
        print("  %s  %s(%s,%s 元/%s)" % (r["next"], r["merchant"], r["category"], r["amount"], r["cycle"]))


def cmd_history(args):
    db.use(args.db)
    rows = db.ledgers(args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("还没有记录。`python -m dingyue scan --file bill.txt --save` 存一条。")
        return
    print("📚 台账历史")
    for r in rows:
        print("  #%d  %d 项  年化 %s 元  %s" % (r["id"], r["count"], r["total"], r["created_at"]))


def cmd_web(args):
    from . import web
    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser():
    p = argparse.ArgumentParser(prog="dingyue", description="订阅 · 账单:归一、年化、续费日、重复与砍单。")
    p.add_argument("--version", action="version", version="dingyue %s" % __version__)
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true")
    p.add_argument("--model", help="覆盖 LLM_MODEL")
    p.add_argument("--base-url", help="覆盖 LLM_BASE_URL")
    p.add_argument("--api-key", help="覆盖 LLM_API_KEY")
    p.add_argument("--db", help="SQLite 路径")
    p.add_argument("--uses", action="append", help="月使用次数,形如 爱奇艺:8")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("scan", help="扫账单")
    sp.add_argument("--text", help="账单文本")
    sp.add_argument("--file", help="从文件读")
    sp.add_argument("--uses", action="append", help="月使用次数,形如 爱奇艺:8")
    sp.add_argument("--save", action="store_true")
    sp.set_defaults(func=cmd_scan)

    mp = sub.add_parser("merchant", help="查商户归一与取消路径")
    mp.add_argument("--name", required=True)
    mp.set_defaults(func=cmd_merchant)

    np_ = sub.add_parser("next", help="看续费日历")
    np_.add_argument("--text")
    np_.add_argument("--file")
    np_.set_defaults(func=cmd_next)

    hp = sub.add_parser("history", help="台账历史")
    hp.add_argument("--limit", type=int, default=10)
    hp.set_defaults(func=cmd_history)

    wp = sub.add_parser("web", help="启动 Web 界面")
    wp.add_argument("--host", default="127.0.0.1")
    wp.add_argument("--port", type=int, default=8000)
    wp.add_argument("--mock", action="store_true", default=argparse.SUPPRESS)
    wp.set_defaults(func=cmd_web)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.mock and args.command == "scan" and not llm.default_config().get("api_key"):
        print(BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print("❌ %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
