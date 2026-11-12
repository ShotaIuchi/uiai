from __future__ import annotations

from pathlib import Path

import pytest

from uiai.platform import PlatformError, candidates, resolve, target
from uiai.redact import Redactor
from uiai.scenario import check_file, fill_secrets, load, render

REPO = Path(__file__).resolve().parents[2]


def write(tmp_path, text):
    p = tmp_path / "s.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def codes(issues):
    return sorted(i.code for i in issues)


def test_samples_pass_check():
    for p in sorted((REPO / "sample").glob("*.yaml")):
        errs = [i for i in check_file(p) if i.level == "error"]
        assert errs == [], (p, errs)


def test_replay_expands_recursively_and_skips_then(tmp_path):
    sc = load(write(tmp_path, """
name: r
app: com.example.app
steps:
  - id: 初期化
    actions:
      - do: "起動"
      - then: "ホーム"
  - id: ログイン
    replay: {from: 初期化, to: 初期化}
    actions:
      - do: "ログイン"
  - id: 確認
    replay: {from: ログイン, to: ログイン}
    actions:
      - then: "OK"
"""))
    last = sc.sections[2].items
    assert [(i.kind, i.raw, i.origin) for i in last] == [
        ("do", "起動", "初期化"), ("do", "ログイン", "ログイン"), ("then", "OK", "確認")]
    assert [i.index for i in sc.items] == list(range(len(sc.items)))


def test_variables_render_and_secrets(tmp_path):
    sc = load(write(tmp_path, r"""
name: v
app: com.example.app
variables:
  email: a@b.c
  pw: {value: s3cret, secret: true}
steps:
  - id: s
    actions:
      - do: '「(email)」と「(pw)」を入力、\(1+2\)'
      - then: "(email) でログイン"
"""))
    vals = {"email": "a@b.c", "pw": "s3cret"}
    assert render(sc.items[0].raw, vals, sc.secret_names) == "「a@b.c」と「(pw)」を入力、(1+2)"
    assert fill_secrets("(pw)!", vals, sc.secret_names) == "s3cret!"
    assert Redactor(["s3cret"])({"a": ["x s3cret y"]}) == {"a": ["x **** y"]}


@pytest.mark.parametrize("body,code", [
    ("variables: {pw: {value: x, secret: true}}\nsteps: [{id: s, actions: [{do: a}, {then: '(pw) が出る'}]}]", "E033"),
    ("steps: [{id: s, actions: [{do: a}, {then: b, verify: ai}]}]", "W007"),
    ("config: {timeout: 5}\nsteps: [{id: s, actions: [{do: a}, {then: b}]}]", "W008"),
    ("config: {on_failure: never}\nsteps: [{id: s, actions: [{do: a}, {then: b}]}]", "E016"),
    ("config: {interrupts: {mode: x}}\nsteps: [{id: s, actions: [{do: a}, {then: b}]}]", "E016"),
    ("steps: [{id: s, actions: [{do: a}, {then: b, timeout: -1}]}]", "E015"),
    ("steps: [{id: a, replay: {from: b, to: b}, actions: [{do: x}]}, {id: b, replay: {from: a, to: a}, actions: [{do: y}]}]", "E023"),
    ("variables:\n  x: 1\n  x: 2\nsteps: [{id: s, actions: [{do: '(x)'}, {then: b}]}]", "E032"),
    ("steps: [{id: s, actions: [{do: '(nope)'}, {then: b}]}]", "E030"),
])
def test_check_rules(tmp_path, body, code):
    p = write(tmp_path, "name: n\napp: com.example.app\n" + body)
    assert code in codes(check_file(p))


@pytest.mark.parametrize("app,ok", [
    ("https://example.com", True), ("web-demo/index.html?bug=1", True), ("com.example.app", True),
    ("example", False), ({"web": "./a.html", "android": "com.a.b"}, True), ({"desktop": "x"}, False),
])
def test_app_format(tmp_path, app, ok):
    import json
    p = write(tmp_path, f"name: n\napp: {json.dumps(app)}\nsteps: [{{id: s, actions: [{{do: a}}, {{then: b}}]}}]")
    assert ("E010" not in codes(check_file(p))) == ok


def test_system_prompt_mentions_secret_placeholders_only_when_present():
    # An example placeholder in the prompt was typed literally by the AI in a scenario without secrets.
    from uiai.ai.protocol import system_prompt
    assert "placeholder" not in system_prompt("x", 1, 1, [])
    assert "(pw)" in system_prompt("x", 1, 1, [], ["pw"])


def test_platform_candidates_and_resolution(tmp_path):
    assert candidates("https://x") == ["web"]
    assert candidates("a/b.html#x") == ["web"]
    assert candidates("com.example.app") == ["android", "ios"]
    assert candidates({"web": "x", "ios": "a.b.c"}) == ["ios", "web"]
    avail = {"android": True, "ios": False, "web": True}
    assert resolve("com.example.app", None, avail) == ["android"]
    with pytest.raises(PlatformError, match="複数"):
        resolve("com.example.app", None, {"android": True, "ios": True, "web": True})
    assert resolve("com.example.app", "all", {"android": True, "ios": True, "web": True}) == ["android", "ios"]
    with pytest.raises(PlatformError, match="実行できる対象がない"):
        resolve("com.example.app", None, {"android": False, "ios": False, "web": True})
    with pytest.raises(PlatformError):
        resolve("https://x", "android", avail)
    assert target("web-demo/index.html?bug=1", "web", tmp_path).endswith("/web-demo/index.html?bug=1")
    assert target("https://x/y", "web", tmp_path) == "https://x/y"
    assert target({"android": "com.a.b"}, "android", tmp_path) == "com.a.b"
