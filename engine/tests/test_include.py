"""`include` in `steps`: the sections of another scenario, optionally on another device (`on`)."""

from __future__ import annotations

import json

import pytest

from conftest import FakeAI, FakeDriver, reply, v
from uiai.scenario import check_file, load, resolve_variables

LOGIN = """
name: ログイン
app: {android: com.example.app}
variables:
  email: login@example.com
  password: {env: PW, secret: true}
steps:
  - id: 入力
    actions:
      - do: "「(email)」と「(password)」でログインする"
      - then: "ホーム画面が表示されていること"
  - id: もう一度
    replay: {from: 入力, to: 入力}
    actions:
      - then: "ホーム画面が表示されていること"
"""

APPROVE = """
name: 承認
app: {web: admin.html, android: com.example.app}
steps:
  - id: 承認する
    actions:
      - do: "管理画面を開いて承認する"
      - then: "「承認しました」と表示されていること"
  - id: 確認
    on: android
    actions:
      - then: "通知が届いていること"
"""


def write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def main(tmp_path, steps: str, extra: str = "") -> object:
    write(tmp_path, "parts/login.yaml", LOGIN)
    write(tmp_path, "parts/approve.yaml", APPROVE)
    return write(tmp_path, "main.yaml", f"name: 本体\napp: {{android: com.example.app}}\n{extra}steps:\n{steps}")


def codes(p):
    return [(i.code, i.message) for i in check_file(p) if i.level == "error"]


# ---------------------------------------------------------------- loading


def test_the_sections_come_in_place_with_their_ids_prefixed(tmp_path):
    p = main(tmp_path, '  - include: parts/login.yaml\n'
                       '  - id: 本題\n    actions: [{do: "設定を開く"}, {then: "設定が開いていること"}]\n')
    sc = load(p)
    assert [s.id for s in sc.sections] == ["ログイン/入力", "ログイン/もう一度", "本題"]
    assert [(it.kind, it.section, it.origin) for it in sc.items] == [
        ("do", "ログイン/入力", "ログイン/入力"), ("then", "ログイン/入力", "ログイン/入力"),
        ("do", "ログイン/もう一度", "ログイン/入力"), ("then", "ログイン/もう一度", "ログイン/もう一度"),  # its replay
        ("do", "本題", "本題"), ("then", "本題", "本題")]
    assert sc.config.timeout == 600 and sc.app == {"android": "com.example.app"}


def test_an_id_names_the_include_so_that_a_scenario_can_be_included_twice(tmp_path):
    p = main(tmp_path, "  - include: parts/login.yaml\n  - include: parts/login.yaml\n")
    assert any(c == "E011" for c, _ in codes(p))  # the same section ids twice
    p = main(tmp_path, "  - include: parts/login.yaml\n  - id: 再ログイン\n    include: parts/login.yaml\n")
    assert codes(p) == [] and [s.id for s in load(p).sections][2:] == ["再ログイン/入力", "再ログイン/もう一度"]


def test_on_runs_the_included_sections_on_that_device_unless_they_name_one(tmp_path):
    p = main(tmp_path, "  - include: parts/approve.yaml\n    on: web\n  - include: parts/login.yaml\n")
    sc = load(p)
    assert [(s.id, s.on) for s in sc.sections] == [
        ("承認/承認する", "web"), ("承認/確認", "android"), ("ログイン/入力", None), ("ログイン/もう一度", None)]
    assert sc.on_platforms == {"web", "android"}


def test_the_included_scenario_keeps_its_own_targets_and_adds_missing_platforms(tmp_path):
    p = main(tmp_path, "  - include: parts/approve.yaml\n    on: web\n")
    sc = load(p)
    admin = (tmp_path / "parts" / "admin.html").resolve().as_uri()  # relative to the file that names it
    assert sc.app == {"android": "com.example.app", "web": admin}
    assert sc.sections[0].targets == {"web": admin, "android": "com.example.app"}


def test_platforms_added_by_an_include_are_not_candidates_for_the_run(tmp_path):
    from uiai.platform import resolve

    write(tmp_path, "parts/both.yaml", 'name: 両方\napp: {android: com.example.app, ios: com.example.App}\n'
                                       'steps:\n  - id: a\n    actions: [{do: "開く"}, {then: "開いた"}]\n')
    p = main(tmp_path, "  - include: parts/both.yaml\n")
    sc = load(p)
    assert sc.app == {"android": "com.example.app", "ios": "com.example.App"}
    every = {"android": True, "ios": True, "web": True}
    assert resolve(sc.run_app, None, every, [s.on for s in sc.sections]) == ["android"]  # not "several"
    assert load(main(tmp_path, '  - id: a\n    actions: [{do: "開く"}]\n')).run_app == {"android": "com.example.app"}


def test_variables_of_the_including_scenario_win_and_secret_stays_secret(tmp_path):
    p = main(tmp_path, "  - include: parts/login.yaml\n",
             'variables:\n  email: me@example.com\n  password: "pw"\n')
    sc = load(p)
    assert sc.variables["email"].value == "me@example.com" and not sc.variables["email"].secret
    assert sc.variables["password"].value == "pw" and sc.variables["password"].secret  # never sent to the AI
    values, missing = resolve_variables(sc, {}, interactive=False)
    assert values == {"email": "me@example.com", "password": "pw"} and missing == []


def test_includes_nest_and_a_cycle_is_an_error(tmp_path):
    write(tmp_path, "a.yaml", "name: A\napp: com.example.app\nsteps:\n  - include: b.yaml\n"
                              "  - id: a1\n    actions: [{do: x}, {then: y}]\n")
    write(tmp_path, "b.yaml", "name: B\napp: com.example.app\nsteps:\n  - include: c.yaml\n"
                              "  - id: b1\n    actions: [{do: x}, {then: y}]\n")
    write(tmp_path, "c.yaml", "name: C\napp: com.example.app\nsteps:\n  - id: c1\n    actions: [{do: x}, {then: y}]\n")
    assert [s.id for s in load(tmp_path / "a.yaml").sections] == ["B/C/c1", "B/b1", "a1"]
    write(tmp_path, "c.yaml", "name: C\napp: com.example.app\nsteps:\n  - include: a.yaml\n")
    (c, m), = codes(tmp_path / "a.yaml")
    assert c == "E042" and "E041" in m and "a.yaml → b.yaml → c.yaml → a.yaml" in m


@pytest.mark.parametrize("entry,code,text", [
    ("  - include: parts/none.yaml\n", "E040", "読み込めない"),
    ("  - include: 3\n", "E040", "パス"),
    ("  - include: parts/login.yaml\n    actions: [{do: x}]\n", "E043", "actions"),
    ("  - include: parts/login.yaml\n    on: mac\n", "E017", "`on`"),
    ("  - include: parts/bad.yaml\n", "E042", "E001 `name` がない"),
])
def test_include_problems(tmp_path, entry, code, text):
    write(tmp_path, "parts/bad.yaml", "app: com.example.app\nsteps: [{id: a, actions: [{do: x}]}]\n")
    p = main(tmp_path, entry + '  - id: 本題\n    actions: [{do: "a"}, {then: "b"}]\n')
    found = codes(p)
    assert [c for c, _ in found] == [code] and text in found[0][1]


def test_an_include_on_a_platform_no_app_has_is_e018(tmp_path):
    p = main(tmp_path, "  - include: parts/login.yaml\n    on: ios\n")
    assert {c for c, _ in codes(p)} == {"E018"}


# ---------------------------------------------------------------- runner


class Recorder(FakeDriver):
    def __init__(self, log, tag):
        super().__init__()
        self.log, self.tag = log, tag

    def reset(self, app, cfg):
        self.log.append(f"{self.tag}:reset:{app}")

    def stop_app(self, app):
        self.log.append(f"{self.tag}:stop:{app}")

    def act(self, action, app, check_stale=False):
        self.log.append(f"{self.tag}:{action['type']}:{app}")
        return super().act(action, app, check_stale)


def passing(msg, n):
    thens = json.loads(msg.split("then to judge now: ")[1].split("\n")[0]) if "then to judge now: " in msg else []
    return reply({"type": "none" if "only judge" in msg else "launch"}, verify=[v(t) for t in thens])


def test_included_sections_run_on_their_device_with_their_own_app(tmp_path, make_run):
    write(tmp_path, "parts/admin.yaml", 'name: 管理\napp: {web: "http://admin"}\n'
                                        'steps:\n  - id: 承認\n    actions: [{do: "承認する"}, {then: "承認済み"}]\n')
    write(tmp_path, "parts/other.yaml", 'name: 別アプリ\napp: {android: com.example.other}\n'
                                        'steps:\n  - id: 開く\n    actions: [{do: "開く"}, {then: "開いた"}]\n')
    log: list[str] = []
    phone, browser = Recorder(log, "android"), Recorder(log, "web")
    y = ('name: 本体\napp: {android: com.example.app, web: "http://shop"}\nconfig: {stop_app_after: true}\nsteps:\n'
         '  - id: 申請\n    actions: [{do: "申請する"}, {then: "申請中"}]\n'
         f'  - include: {tmp_path}/parts/admin.yaml\n    on: web\n'
         f'  - include: {tmp_path}/parts/other.yaml\n'
         '  - id: 結果\n    actions: [{do: "開いて確かめる"}, {then: "承認済み"}]\n')
    res, *_ = make_run(y, passing, driver=phone, platform="android", others={"web": (browser, "http://shop")})
    assert res.status == "pass", [(s.section, s.status, s.reason) for s in res.steps]
    assert [x for x in log if ":launch:" in x] == [
        "android:launch:http://x", "web:launch:http://admin",   # not the scenario's own web target
        "android:launch:com.example.other", "android:launch:http://x"]  # (make_run's target for the phone)
    resets = [x for x in log if ":reset:" in x]
    assert resets == ["android:reset:http://x", "web:reset:http://shop", "web:reset:http://admin",
                      "android:reset:com.example.other"]  # every app starts reset, and is stopped at the end
    assert sorted(x for x in log if ":stop:" in x) == sorted(r.replace(":reset:", ":stop:") for r in resets)
    assert [s.platform for s in res.steps] == ["android"] * 2 + ["web"] * 2 + ["android"] * 4


def test_dry_run_with_an_include_on_another_device(tmp_path, monkeypatch, capsys):
    from uiai import cli, platform

    monkeypatch.setattr(platform, "probe", lambda serial=None, udid=None: {"android": True, "ios": True, "web": True})
    p = main(tmp_path, "  - include: parts/approve.yaml\n    on: web\n"
                       '  - id: 結果\n    actions: [{do: "開く"}, {then: "承認済み"}]\n')
    assert cli.main(["run", str(p), "--dry-run"]) == 0
    assert "android で実行できる（`on` で web にも切り替える）" in capsys.readouterr().out
