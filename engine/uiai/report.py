"""Results: result.json, report.md, report.html per scenario; summary.md per run."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .loop import STATUS_LABEL, ScenarioResult
from .redact import Redactor

ICON = {"pass": "✅", "pass_warn": "⚠️", "fail": "❌", "error": "💥", "skipped": "⏭️", "not_run": "—"}


def _md(s: object) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def write_scenario(res: ScenarioResult, out: Path, redact: Redactor) -> None:
    data = redact(asdict(res))
    data["counts"] = res.counts()
    (out / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(redact.text(_report_md(res)), encoding="utf-8")
    (out / "report.html").write_text(redact.text(_report_html(res)), encoding="utf-8")


def _meta_lines(res: ScenarioResult) -> list[str]:
    c = res.counts()
    tokens = max((x["in_tokens"] for x in res.calls), default=0)
    sessions = len({x.get("session", 1) for x in res.calls})
    return [
        f"- 結果: {ICON[res.status]} {STATUS_LABEL[res.status]}" + (f" — {res.error}" if res.error else ""),
        f"- ステップ: 合格 {c['pass']}・不合格 {c['fail']}・未実行 {c['not_run']}・警告 {c['warnings']}",
        f"- シナリオ: `{res.file}`",
        f"- 対象: {res.platform}（{res.target}）",
        f"- モデル: {res.model}・AI 呼び出し {len(res.calls)} 回（会話 {sessions} 本）・1 回の入力は最大 {tokens} トークン",
        f"- 開始: {res.started_at}・所要 {res.seconds} 秒",
    ]


def _report_md(res: ScenarioResult) -> str:
    lines = [f"# {res.name} @ {res.platform}", "", *_meta_lines(res), "", "## ステップ", "",
             "| # | セクション | 種別 | 内容 | 結果 | 理由・読み取った文字 | 警告・メモ |", "|---|---|---|---|---|---|---|"]
    for s in res.steps:
        why = s.reason + (f"（読み取り: {s.read}）" if s.read else "")
        extra = "; ".join([f"⚠️ {w}" for w in s.warnings] + s.notes)
        sec = s.section + (f"（replay: {s.origin}）" if s.origin != s.section else "")
        lines.append(f"| {s.index + 1} | {_md(sec)} | {s.kind}{' [strict]' if s.strict else ''} | {_md(s.text)} "
                     f"| {ICON[s.status]} {STATUS_LABEL[s.status]} | {_md(why)} | {_md(extra)} |")
    if res.check_warnings:
        lines += ["", "## シナリオ形式の警告", "", *[f"- {w}" for w in res.check_warnings]]
    lines += ["", "## AI 呼び出し", "", "| # | 時刻 | 種類 | 操作 | 結果 | 撮影 | AI |", "|---|---|---|---|---|---|---|"]
    for c in res.calls:
        a = c["action"] or {}
        op = a.get("type", "") + (f" ({a.get('x')},{a.get('y')})" if "x" in a else "") + \
            (f" {a.get('text')!r}" if a.get("type") == "input" else "")
        lines.append(f"| {c['n']} | {c['t']}s | {c['kind']}/{c['purpose']} | {_md(op)} | {_md(c['act_result'])} "
                     f"| {c['obs_s']}s | {c['llm_s']}s |")
    return "\n".join(lines) + "\n"


CSS = """
:root{--bg:#f7f8fa;--fg:#1d2330;--card:#fff;--muted:#667085;--border:#d9dee7;--pass:#12805c;--fail:#c4320a;--warn:#b54708}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8ebf0;--card:#1f242c;--muted:#9aa3b2;--border:#353c47;--pass:#4fd1a1;--fail:#ff8c6b;--warn:#fdb022}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP","Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 8px}h2{font-size:16px;margin:28px 0 8px}
ul.meta{margin:0;padding-left:18px;color:var(--muted)}
table{border-collapse:collapse;width:100%;background:var(--card)}
td,th{border:1px solid var(--border);padding:6px 8px;vertical-align:top;text-align:left}
.pass{color:var(--pass)}.fail{color:var(--fail)}.warn{color:var(--warn)}.not_run{color:var(--muted)}
.calls{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.call{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px}
.shot{position:relative;display:block}.shot img{width:100%;height:auto;display:block;border-radius:4px;border:1px solid var(--border)}
.mark{position:absolute;width:22px;height:22px;margin:-11px 0 0 -11px;border:3px solid #ff2d55;border-radius:50%;box-shadow:0 0 0 2px #fff}
.small{font-size:12px;color:var(--muted)}code{font-size:12px}
"""


def _report_html(res: ScenarioResult) -> str:
    e = html.escape
    meta = "".join(f"<li>{e(m[2:])}</li>" for m in _meta_lines(res))
    rows = []
    for s in res.steps:
        cls = "warn" if s.status == "pass" and s.warnings else s.status
        why = e(s.reason) + (f"<br><span class=small>読み取り: <code>{e(s.read)}</code></span>" if s.read else "")
        extra = "<br>".join([f"<span class=warn>⚠️ {e(w)}</span>" for w in s.warnings] + [e(n) for n in s.notes])
        calls = " ".join(f'<a href="#c{n}">#{n}</a>' for n in s.calls)
        rows.append(f"<tr><td>{s.index + 1}</td><td>{e(s.section)}</td><td>{s.kind}{' [strict]' if s.strict else ''}</td>"
                    f"<td>{e(s.text)}</td><td class={cls}>{ICON[s.status]} {STATUS_LABEL[s.status]}</td>"
                    f"<td>{why}</td><td>{extra}</td><td>{calls}</td></tr>")
    cards = []
    for c in res.calls:
        a = c["action"] or {}
        mark = ""
        if "x" in a and "y" in a and c["iw"]:
            try:
                left, top = float(a["x"]) / c["iw"] * 100, float(a["y"]) / c["ih"] * 100
                mark = f'<span class=mark style="left:{left:.2f}%;top:{top:.2f}%"></span>'
            except (TypeError, ValueError):
                pass
        verdicts = "".join(
            f"<li class={'pass' if v.get('pass') else 'fail'}>{'✅' if v.get('pass') else '❌'} {e(str(v.get('then', '')))}"
            f" — {e(str(v.get('reason', '')))}" + (f" <code>{e(str(v['read']))}</code>" if v.get("read") else "") + "</li>"
            for v in c["verify"])
        verdicts += "".join(
            f"<li class={'pass' if r.get('pass') else 'fail'}>↻ 再判定（{e(str(r.get('model')))}）"
            f"{'✅' if r.get('pass') else '❌'} {e(str(r.get('then', '')))} — {e(str(r.get('reason', '')))}"
            + (f" <code>{e(str(r['read']))}</code>" if r.get("read") else "") + f" · {r.get('llm_s')}s</li>"
            for r in c.get("rejudge", []))
        op = e(a.get("type", "")) + (f" ({e(str(a.get('x')))},{e(str(a.get('y')))})" if "x" in a else "") + \
            (f" <code>{e(str(a.get('text', '')))}</code>" if a.get("type") == "input" else "") + \
            (f" <code>{e(str(a.get('key', '')))}</code>" if a.get("type") == "key" else "")
        tag = {"interrupt": " [割り込み]", "verify": " [判定のため]"}.get(c["purpose"], "")
        cards.append(
            f'<div class=call id="c{c["n"]}"><div class=small>#{c["n"]} · {c["t"]}s · {e(c["section"])} · {c["kind"]}</div>'
            f'<div><b>{e(c["do"]) if c["do"] else "（判定のみ）"}</b></div>'
            f'<a class=shot href="{c["image"]}">{mark}<img src="{c["image"]}" alt="call {c["n"]}"></a>'
            f'<div>{op}{tag}' + (f' → {e(c["act_result"])}' if c["act_result"] not in ("", "ok") else "") + "</div>"
            + (f'<div class=small>理由: {e(str(a.get("reason", "")))}</div>' if a.get("reason") else "")
            + (f'<div class=small>ダイアログ: {e(c["dialog"])}</div>' if c["dialog"] else "")
            + (f"<ul>{verdicts}</ul>" if verdicts else "")
            + (f'<div class=small>{e(c["note"])}</div>' if c["note"] else "")
            + f'<div class=small>撮影 {c["obs_s"]}s · AI {c["llm_s"]}s · 入力 {c["in_tokens"]} トークン'
              f' · 会話 {c.get("session", 1)}</div></div>')
    cw = "".join(f"<li>{e(w)}</li>" for w in res.check_warnings)
    return (f"<!doctype html><html lang=ja><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(res.name)} @ {res.platform}</title><style>{CSS}</style></head><body><main>"
            f"<h1>{e(res.name)} @ {res.platform}</h1><ul class=meta>{meta}</ul>"
            f"<h2>ステップ</h2><table><tr><th>#</th><th>セクション</th><th>種別</th><th>内容</th><th>結果</th>"
            f"<th>理由</th><th>警告・メモ</th><th>呼び出し</th></tr>{''.join(rows)}</table>"
            + (f"<h2>シナリオ形式の警告</h2><ul>{cw}</ul>" if cw else "")
            + f"<h2>AI 呼び出し（AI に送った画像と操作位置）</h2><div class=calls>{''.join(cards)}</div>"
            "</main></body></html>")


def write_summary(results: list[tuple[ScenarioResult, Path]], run_dir: Path, exit_code: int,
                  skipped: list[tuple[str, str]], redact: Redactor) -> Path:
    lines = ["# uiai 実行結果", "", f"- 終了コード: {exit_code}", "",
             "| シナリオ | 対象 | 結果 | 合格 | 不合格 | 未実行 | 警告 | 秒 | レポート |", "|---|---|---|---|---|---|---|---|---|"]
    for res, out in results:
        c = res.counts()
        rel = out.relative_to(run_dir).as_posix()
        lines.append(f"| {_md(res.name)} | {res.platform} | {ICON[res.status]} {STATUS_LABEL[res.status]} | {c['pass']} "
                     f"| {c['fail']} | {c['not_run']} | {c['warnings']} | {res.seconds} | [{rel}/report.md]({rel}/report.md) |")
    for name, reason in skipped:
        lines.append(f"| {_md(name)} | — | {ICON['skipped']} 未実行 | | | | | | {_md(reason)} |")
    fails = [(r, s) for r, _ in results for s in r.steps if s.status == "fail"]
    if fails:
        lines += ["", "## 失敗", ""]
        lines += [f"- {r.name} @ {r.platform} / {s.section} / {s.kind}「{s.text}」: {s.reason}"
                  + (f"（読み取り: {s.read}）" if s.read else "") for r, s in fails]
    errs = [r for r, _ in results if r.status == "error"]
    if errs:
        lines += ["", "## 実行エラー", ""] + [f"- {r.name} @ {r.platform}: {r.error}" for r in errs]
    warns = [(r, s, w) for r, _ in results for s in r.steps for w in s.warnings]
    if warns:
        lines += ["", "## 警告", ""] + [f"- {r.name} @ {r.platform} / {s.section} / 「{s.text}」: {w}" for r, s, w in warns]
    p = run_dir / "summary.md"
    p.write_text(redact.text("\n".join(lines) + "\n"), encoding="utf-8")
    return p
