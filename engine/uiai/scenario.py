"""Scenario YAML: loading, validation (`uiai check`), variables and replay expansion."""

from __future__ import annotations

import getpass
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VAR_RE = re.compile(r"(?<!\\)\(([a-zA-Z_][a-zA-Z0-9_]*)\)")
NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_-]*)+$")  # Android は 2 区切り以上（com.whatsapp など）
URL_RE = re.compile(r"^https?://", re.I)

PLATFORMS = ("android", "ios", "web")
ON_FAILURE = ("stop_scenario", "next_section", "stop_all")
INTERRUPT_MODES = ("allow", "report", "fail")
CONFIG_KEYS = {
    "timeout", "clear_data_before", "stop_app_after", "strict", "verify",
    "then_timeout", "max_actions", "interrupts", "on_failure", "reset", "model", "type_delay",
}
INCLUDE_KEYS = {"include", "id", "on"}
DEFAULT_TIMEOUT = 600.0
DEFAULT_THEN_TIMEOUT = 5.0
DEFAULT_OBSERVE = 2.0
DEFAULT_MAX_ACTIONS = 5
SECONDS_PER_DO_HINT = 10  # W008: config.timeout smaller than (#do x this) is probably too short


class ScenarioError(Exception):
    """The scenario cannot be run (format errors). `issues` holds the details."""

    def __init__(self, path: Path, issues: list["Issue"]):
        self.path, self.issues = path, issues
        super().__init__("; ".join(f"{i.code} {i.message}" for i in issues if i.level == "error"))


@dataclass
class Issue:
    code: str
    level: str  # "error" | "warning"
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = f" ({self.where})" if self.where else ""
        return f"{self.code} [{'エラー' if self.level == 'error' else '警告'}] {self.message}{loc}"


@dataclass
class Variable:
    name: str
    value: str | None = None
    env: str | None = None
    prompt: str | None = None
    secret: bool = False

    @property
    def is_placeholder(self) -> bool:
        """Needs a value at run time (interactive input, --var, or the env var)."""
        return self.value is None


@dataclass
class Interrupts:
    mode: str = "report"
    allow: list[str] = field(default_factory=list)


@dataclass
class Config:
    timeout: float = DEFAULT_TIMEOUT
    then_timeout: float = DEFAULT_THEN_TIMEOUT
    max_actions: int = DEFAULT_MAX_ACTIONS
    interrupts: Interrupts = field(default_factory=Interrupts)
    on_failure: str = "stop_scenario"
    reset: list[str] = field(default_factory=list)
    model: str | None = None
    type_delay: float = 0.0  # ms between typed characters; 0 = as fast as the platform types
    clear_data_before: bool = False
    stop_app_after: bool = False
    strict: bool = False


@dataclass
class Item:
    """One `do` or `then` line, in run order, after replay expansion."""

    kind: str               # "do" | "then"
    raw: str                # as written (variables not substituted)
    section: str            # section that runs it
    origin: str             # section where it is written (differs for replayed `do`)
    strict: bool = False
    optional: bool = False  # do only: if it fails, it is recorded as skipped and the scenario goes on
    wait: float = 0.0
    timeout: float = DEFAULT_THEN_TIMEOUT   # then only
    observe: float = DEFAULT_OBSERVE        # then only
    index: int = 0          # position in the whole scenario (0-based)

    @property
    def replayed(self) -> bool:
        return self.origin != self.section


@dataclass
class Section:
    id: str
    items: list[Item]
    on: str | None = None   # the platform it runs on; None: the one chosen for the run
    # included sections: {platform: target} of the scenario they come from (it wins over `Scenario.app`)
    targets: dict[str, str] = field(default_factory=dict)


@dataclass
class Scenario:
    path: Path
    name: str
    app: Any
    config: Config
    variables: dict[str, Variable]
    sections: list[Section]
    warnings: list[Issue] = field(default_factory=list)
    # the `app` of the file itself: what the run's platform is chosen from (`app` also has the platforms that
    # included scenarios add, for their sections)
    own_app: Any = None

    @property
    def run_app(self) -> Any:
        return self.app if self.own_app is None else self.own_app

    @property
    def items(self) -> list[Item]:
        return [it for s in self.sections for it in s.items]

    @property
    def secret_names(self) -> set[str]:
        return {n for n, v in self.variables.items() if v.secret}

    def untargeted(self, platform: str) -> list[str]:
        """Included sections that would run, in a run on `platform`, where their own scenario has no target."""
        return [s.id for s in self.sections if s.targets and (s.on or platform) not in s.targets]

    @property
    def on_platforms(self) -> set[str]:
        """Platforms named by sections' `on`."""
        return {s.on for s in self.sections if s.on}


# --------------------------------------------------------------------------- #
# YAML loading (with duplicate-key detection for E032)
# --------------------------------------------------------------------------- #


class _Loader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        # YAML 1.1 reads a plain `on` as true: as a key it is the section's `on` (values are left alone)
        if isinstance(key_node, yaml.ScalarNode) and key_node.tag == "tag:yaml.org,2002:bool" \
                and key_node.style is None and key_node.value in ("on", "On", "ON"):
            key_node.tag = "tag:yaml.org,2002:str"
            key_node.value = "on"
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            loader.duplicates.append((key, key_node.start_mark.line + 1))
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


@dataclass
class _Step:
    """Where an entry of the expanded `steps` comes from (for messages), and the targets of an included one."""
    where: str                    # its place in the file: `steps[i]`, or the `include` that brought it
    targets: dict[str, str] = field(default_factory=dict)  # included: {platform: target} of its own scenario
    scenario: str = ""            # included: the name of the scenario it is written in


@dataclass
class _Read:
    data: Any                     # with the `include`s expanded
    duplicates: list[tuple[Any, int]]
    steps: list[_Step]            # one per entry of data["steps"]
    own_app: Any                  # the file's own `app` (data["app"] also has the platforms includes add)
    issues: list["Issue"]         # problems with the `include`s


def _read_scenario(path: Path, parents: tuple[Path, ...] = ()) -> _Read:
    """Read a scenario and replace each `include` entry of `steps` with the sections of that scenario: ids
    prefixed with the entry's `id` (else the scenario's name) and `/`, the entry's `on` given to those without
    one, and that scenario's targets kept for them. Its variables and platforms are added where this scenario
    has none; its config is not used. An included scenario must be valid on its own.
    Raises yaml.YAMLError, UnicodeDecodeError or OSError if this file cannot be read."""
    path = path.resolve()
    data, dups = _read_yaml(path)
    issues: list[Issue] = []
    raw = data.get("steps") if isinstance(data, dict) else None
    own_app = data.get("app") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not any(isinstance(s, dict) and "include" in s for s in raw):
        return _Read(data, dups, [_Step(f"steps[{i}]") for i in range(len(raw or []))], own_app, issues)
    from .platform import candidates, target

    def err(code: str, msg: str, where: str) -> None:
        issues.append(Issue(code, "error", msg, where))

    data = dict(data)
    merged_app = None if not isinstance(own_app, (str, dict)) or not own_app else (
        dict(own_app) if isinstance(own_app, dict) else {p: own_app for p in candidates(own_app)})
    variables = data.get("variables") or {}
    variables = dict(variables) if isinstance(variables, dict) else None
    steps: list = []
    metas: list[_Step] = []
    for i, sec in enumerate(raw):
        if not (isinstance(sec, dict) and "include" in sec):
            steps.append(sec)
            metas.append(_Step(f"steps[{i}]"))
            continue
        inc = sec["include"]
        where = f"steps[{i}]（include: {inc}）"
        extra = sorted(str(k) for k in sec if k not in INCLUDE_KEYS)
        if extra:
            err("E043", f"`include` のセクションには `id`・`on` しか書けない（{', '.join(extra)}）", where)
            continue
        if not isinstance(inc, str) or not inc.strip():
            err("E040", "`include` はシナリオファイルのパス（このファイルからの相対パス）", where)
            continue
        if "on" in sec and sec["on"] not in PLATFORMS:
            err("E017", f"`on` は {'/'.join(PLATFORMS)} のいずれか", where)
            continue
        sub_path = (path.parent / inc).resolve()
        if sub_path in (*parents, path):
            err("E041", "`include` が循環している（" + " → ".join(p.name for p in (*parents, path, sub_path)) + "）",
                where)
            continue
        try:
            sub = _read_scenario(sub_path, (*parents, path))
        except yaml.YAMLError as e:
            err("E040", f"`include` 先の YAML の構文エラー: {e}", where)
            continue
        except UnicodeDecodeError as e:
            err("E040", f"`include` 先を UTF-8 として読めない: {e}", where)
            continue
        except OSError as e:
            err("E040", f"`include` 先を読み込めない: {e}", where)
            continue
        bad = [x for x in sub.issues + check_data(sub.data, sub.duplicates, sub.steps, sub.own_app)
               if x.level == "error"]
        if bad:
            err("E042", "`include` 先のシナリオにエラーがある: " + "; ".join(
                f"{x.code} {x.message}" + (f"（{x.where}）" if x.where else "") for x in bad), where)
            continue
        name, app = str(sub.data["name"]), sub.data["app"]
        prefix = str(sec.get("id") or name)
        sub_targets = {p: target(app, p, sub_path.parent) for p in candidates(app)}
        if merged_app is not None:
            for p, t in sub_targets.items():
                merged_app.setdefault(p, t)
        if variables is not None:
            for n, spec in (sub.data.get("variables") or {}).items():
                if n not in variables:
                    variables[n] = spec
                elif parse_variable(n, spec).secret and not parse_variable(n, variables[n]).secret:
                    variables[n] = _as_secret(variables[n])  # secret if either side says so
        for s, m in zip(sub.data["steps"], sub.steps):
            s = dict(s, id=f"{prefix}/{s['id']}")
            if isinstance(s.get("replay"), dict):
                r = s["replay"]
                s["replay"] = dict(r, **{k: f"{prefix}/{r[k]}" for k in ("from", "to")})
            if "on" not in s and "on" in sec:
                s["on"] = sec["on"]
            steps.append(s)
            # sections it included itself keep their own scenario's targets
            metas.append(_Step(where, {**sub_targets, **m.targets}, m.scenario or name))
    data["steps"] = steps
    if merged_app is not None:
        data["app"] = merged_app
    if variables is not None:
        data["variables"] = variables
    return _Read(data, dups, metas, own_app, issues)


def _as_secret(spec: Any) -> Any:
    if isinstance(spec, dict):
        return dict(spec, secret=True)
    return {"secret": True} if spec is None else {"value": spec, "secret": True}


def _read_yaml(path: Path) -> tuple[Any, list[tuple[Any, int]]]:
    loader = _Loader(path.read_text(encoding="utf-8"))
    loader.duplicates = []
    try:
        return loader.get_single_data(), loader.duplicates
    finally:
        loader.dispose()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _strip_query(s: str) -> str:
    return re.split(r"[?#]", s, maxsplit=1)[0]


def is_web_target(s: str) -> bool:
    """A string `app` means Web if it is an http(s)/file URL or a path to an .html file."""
    return (bool(URL_RE.match(s)) or s.lower().startswith("file:")
            or _strip_query(s).lower().endswith((".html", ".htm")))


def check_data(data: Any, duplicates: list[tuple[Any, int]] | None = None, origins: list[_Step] | None = None,
               own_app: Any = None) -> list[Issue]:
    """Validate a parsed scenario. Rule IDs follow skills/scenario-check (E0xx/W0xx).
    origins / own_app: from _read_scenario, when `include`s were expanded (where each step comes from, and
    the file's own `app`)."""
    from .platform import candidates, default_platform

    issues: list[Issue] = []

    def err(code: str, msg: str, where: str = "") -> None:
        issues.append(Issue(code, "error", msg, where))

    def warn(code: str, msg: str, where: str = "") -> None:
        issues.append(Issue(code, "warning", msg, where))

    if not isinstance(data, dict):
        err("E000", "シナリオの最上位がマッピングではない")
        return issues

    if not data.get("name"):
        err("E001", "`name` がない")
    app = data.get("app")
    if not app:
        err("E002", "`app` がない")
    else:
        _check_app(app, err)
    steps = data.get("steps")
    if steps is None:
        err("E003", "`steps` がない")
        steps = []
    elif not isinstance(steps, list) or not steps:
        err("E004", "`steps` が空")
        steps = []

    # config
    cfg = data.get("config") or {}
    if not isinstance(cfg, dict):
        err("E015", "`config` がマッピングではない")
        cfg = {}
    for k in cfg:
        if k not in CONFIG_KEYS:
            warn("W004", f"`config.{k}` は未知のキー")
    for k in ("timeout", "then_timeout", "max_actions"):
        if k in cfg and not (_is_number(cfg[k]) and cfg[k] > 0):
            err("E015", f"`config.{k}` は正の数", f"config.{k}")
    if "type_delay" in cfg and not (_is_number(cfg["type_delay"]) and cfg["type_delay"] >= 0):
        err("E015", "`config.type_delay` は 0 以上の数（ミリ秒）", "config.type_delay")
    for k in ("strict", "clear_data_before", "stop_app_after"):
        if k in cfg and not isinstance(cfg[k], bool):
            err("E014", f"`config.{k}` は true/false", f"config.{k}")
    if "on_failure" in cfg and cfg["on_failure"] not in ON_FAILURE:
        err("E016", f"`config.on_failure` は {'/'.join(ON_FAILURE)} のいずれか", "config.on_failure")
    if "interrupts" in cfg:
        intr = cfg["interrupts"]
        mode = intr if isinstance(intr, str) else (intr or {}).get("mode", "report") if isinstance(intr, dict) else None
        if mode not in INTERRUPT_MODES:
            err("E016", f"`config.interrupts.mode` は {'/'.join(INTERRUPT_MODES)} のいずれか", "config.interrupts")
        if isinstance(intr, dict) and "allow" in intr and not (
                isinstance(intr["allow"], list) and all(isinstance(a, str) for a in intr["allow"])):
            err("E015", "`config.interrupts.allow` は文字列のリスト", "config.interrupts.allow")
    if "reset" in cfg and not (isinstance(cfg["reset"], list) and all(isinstance(a, str) for a in cfg["reset"])):
        err("E015", "`config.reset` は文字列（パッケージ名など）のリスト", "config.reset")
    if "verify" in cfg:
        warn("W007", "`config.verify` は廃止（AI の画像判定に一本化）。無視する", "config.verify")

    # variables
    variables = data.get("variables") or {}
    if not isinstance(variables, dict):
        err("E031", "`variables` がマッピングではない")
        variables = {}
    for key, line in duplicates or []:
        if key in variables:
            err("E032", f"変数 `{key}` が重複している", f"{line} 行目")
    secret_names: set[str] = set()
    for name, spec in variables.items():
        if not isinstance(name, str) or not NAME_RE.match(name):
            err("E031", f"変数名 `{name}` が不正（英字か _ で始まり、英数字と _ のみ）")
            continue
        var = parse_variable(name, spec)
        if var.secret:
            secret_names.add(name)
        if var.is_placeholder and not var.env:
            warn("W006", f"変数 `{name}` は値がなく、実行時に入力が必要（CI では実行されない）")

    # steps
    if origins is None or len(origins) != len(steps):
        origins = [_Step(f"steps[{i}]") for i in range(len(steps))]
    run_app = own_app if own_app is not None else app
    run_cands = candidates(run_app) if isinstance(run_app, (str, dict)) and run_app else []
    ons = [s.get("on") if isinstance(s, dict) and s.get("on") in PLATFORMS else None for s in steps]
    included: set[tuple[str, str]] = set()  # E044 once per include
    ids: list[str] = []
    for i, sec in enumerate(steps):
        where = origins[i].where
        if not isinstance(sec, dict):
            err("E005", "ステップがマッピングではない", where)
            continue
        sid = sec.get("id")
        if sid in (None, ""):
            err("E005", "`id` がない", where)
        else:
            sid = str(sid)
            if sid in ids:
                err("E011", f"`id` 「{sid}」が重複している", where)
            ids.append(sid)
        if "actions" not in sec and "replay" not in sec:
            err("E006", "`actions` がない", where)
        on_ok = True
        if "on" in sec:
            if sec["on"] not in PLATFORMS:
                err("E017", f"`on` は {'/'.join(PLATFORMS)} のいずれか", where)
                on_ok = False
            elif app and sec["on"] not in candidates(app):
                err("E018", f"`on: {sec['on']}` のセクションがあるが、`app` に {sec['on']} の対象がない", where)
                on_ok = False
        o = origins[i]
        if o.targets and on_ok:  # an included section runs with its own scenario's targets: they must cover it
            on = sec.get("on")
            if on in PLATFORMS and on not in o.targets:
                msg = f"`include` した「{o.scenario}」の `app` に {on} の対象がない"
            elif on is None and run_cands and not set(run_cands) & set(o.targets):
                msg = (f"`include` した「{o.scenario}」の `app` に、このシナリオを実行するプラットフォーム"
                       f"（{'/'.join(run_cands)}）の対象がない。`include` に `on` で実行するデバイスを書く")
            else:
                msg = ""
            if msg and (where, msg) not in included:
                included.add((where, msg))
                err("E044", msg, where)

    used_vars: set[str] = set()
    for i, sec in enumerate(steps):
        if not isinstance(sec, dict):
            continue
        where = f"{origins[i].where}（{sec.get('id', '')}）"
        replay = sec.get("replay")
        if replay is not None:
            if not isinstance(replay, dict):
                err("E020", "`replay` は from/to を持つマッピング", where)
            else:
                f, t = str(replay.get("from", "")), str(replay.get("to", ""))
                if f not in ids:
                    err("E020", f"`replay.from` 「{f}」が存在しない", where)
                if t not in ids:
                    err("E021", f"`replay.to` 「{t}」が存在しない", where)
                if f in ids and t in ids and ids.index(f) > ids.index(t):
                    err("E022", f"`replay` の from 「{f}」が to 「{t}」より後にある", where)
                elif f in ids and t in ids:
                    # no `on` = the run's platform: the same device as `on: X` when the run is sure to be on X
                    run = default_platform(run_app, ons) if run_cands else None
                    on_of = {str(s.get("id")): (s.get("on") or run) for s in steps if isinstance(s, dict)}
                    mine = sec.get("on") or run
                    other = [x for x in ids[ids.index(f): ids.index(t) + 1] if on_of.get(x) != mine]
                    if other:
                        warn("W011", f"`replay` の範囲に `on` が違うセクション（{'、'.join(other)}）がある。"
                             "再実行はこのセクションのデバイスで行う", where)
        actions = sec.get("actions")
        if actions is None:
            continue
        if not isinstance(actions, list):
            err("E006", "`actions` がリストではない", where)
            continue
        if not actions and replay is None:
            warn("W001", "`actions` が空", where)
        has_then, prev_then = False, False
        for j, a in enumerate(actions):
            aw = f"{where} actions[{j}]"
            if not isinstance(a, dict):
                err("E034", "アクションがマッピングではない", aw)
                continue
            if "do" in a and "then" in a:
                err("E012", "`do` と `then` が同じ行にある", aw)
            if "do" not in a and "then" not in a:
                err("E034", "`do` も `then` もない", aw)
                continue
            kind = "do" if "do" in a else "then"
            text = a[kind]
            if not isinstance(text, str) or not text.strip():
                err("E034", f"`{kind}` の文が空", aw)
                text = ""
            if "wait" in a and not (_is_number(a["wait"]) and a["wait"] >= 0):
                err("E013", "`wait` は数値（秒）", aw)
            if "strict" in a and not isinstance(a["strict"], bool):
                err("E014", "`strict` は true/false", aw)
            if "optional" in a:
                if not isinstance(a["optional"], bool):
                    err("E014", "`optional` は true/false", aw)
                elif kind != "do":
                    warn("W010", "`optional` は `do` にだけ有効（`then` では無視する）", aw)
            for k in ("timeout", "observe"):
                if k in a:
                    if kind != "then":
                        warn("W009", f"`{k}` は `then` にだけ有効", aw)
                    elif not (_is_number(a[k]) and a[k] >= 0):
                        err("E015", f"`{k}` は 0 以上の数（秒）", aw)
            if "verify" in a:
                warn("W007", "`verify` は廃止（AI の画像判定に一本化）。無視する", aw)
            for m in VAR_RE.finditer(text):
                name = m.group(1)
                used_vars.add(name)
                if name not in variables:
                    err("E030", f"未定義の変数 `({name})`", aw)
                elif kind == "then" and name in secret_names:
                    err("E033", f"秘密の変数 `({name})` は `then` で使えない（AI に値を渡さないため照合できない）", aw)
            if kind == "then":
                has_then = True
                if prev_then:
                    warn("W003", "`then` が連続している", aw)
            prev_then = kind == "then"
        if not has_then and actions:
            warn("W002", "セクションに `then` がない", where)

    if not any(i.code in ("E020", "E021") for i in issues):
        cyc = _find_replay_cycle(steps)
        if cyc:
            err("E023", "`replay` が循環している: " + " → ".join(cyc))

    for name in variables:
        if isinstance(name, str) and name not in used_vars:
            warn("W005", f"変数 `{name}` が使われていない")

    timeout = cfg.get("timeout")
    n_do = sum(1 for s in steps if isinstance(s, dict) for a in (s.get("actions") or [])
               if isinstance(a, dict) and "do" in a)
    if _is_number(timeout) and timeout < n_do * SECONDS_PER_DO_HINT:
        warn("W008", f"`config.timeout`（{timeout} 秒）が短い可能性。AI 方式は 1 ステップ 3〜6 秒かかる"
                     f"（目安: `do` {n_do} 個 × {SECONDS_PER_DO_HINT} 秒 = {n_do * SECONDS_PER_DO_HINT} 秒以上）")
    return issues


def _check_app(app: Any, err) -> None:
    if isinstance(app, str):
        if not (is_web_target(app) or PACKAGE_RE.match(app)):
            err("E010", f"`app` 「{app}」の形式が不正（パッケージ名・Bundle ID、または URL・.html のパス）")
    elif isinstance(app, dict):
        for k, v in app.items():
            if k not in PLATFORMS:
                err("E010", f"`app.{k}` は未知のプラットフォーム（android/ios/web）")
            elif not isinstance(v, str) or not v:
                err("E010", f"`app.{k}` が空")
            elif k == "web" and re.match(r"^[a-z][a-z0-9+.-]+:", v, re.I) and not re.match(r"^(https?|file):", v, re.I):
                err("E010", f"`app.web` 「{v}」は URL（http/https/file）かファイルのパス")
            elif k in ("android", "ios") and not PACKAGE_RE.match(v):
                err("E010", f"`app.{k}` 「{v}」の形式が不正")
    else:
        err("E010", "`app` は文字列か、android/ios/web をキーに持つマッピング")


def _find_replay_cycle(steps: list) -> list[str] | None:
    ids = [str(s.get("id")) for s in steps if isinstance(s, dict)]
    by_id = {str(s.get("id")): s for s in steps if isinstance(s, dict)}

    def refs(sid: str) -> list[str]:
        r = by_id.get(sid, {}).get("replay")
        if not isinstance(r, dict):
            return []
        f, t = str(r.get("from")), str(r.get("to"))
        if f not in ids or t not in ids or ids.index(f) > ids.index(t):
            return []
        return ids[ids.index(f): ids.index(t) + 1]

    def visit(sid: str, stack: list[str]) -> list[str] | None:
        if sid in stack:
            return stack[stack.index(sid):] + [sid]
        for nxt in refs(sid):
            c = visit(nxt, stack + [sid])
            if c:
                return c
        return None

    for sid in ids:
        c = visit(sid, [])
        if c:
            return c
    return None


def check_file(path: Path) -> list[Issue]:
    return _check(path)[0]


def _check(path: Path) -> tuple[list[Issue], _Read | None]:
    try:
        r = _read_scenario(path)
    except yaml.YAMLError as e:
        return [Issue("E000", "error", f"YAML の構文エラー: {e}")], None
    except UnicodeDecodeError as e:
        return [Issue("E000", "error", f"UTF-8 として読めない: {e}")], None
    except OSError as e:
        return [Issue("E000", "error", f"読み込めない: {e}")], None
    return r.issues + check_data(r.data, r.duplicates, r.steps, r.own_app), r


# --------------------------------------------------------------------------- #
# Loading for execution
# --------------------------------------------------------------------------- #


def parse_variable(name: str, spec: Any) -> Variable:
    if isinstance(spec, dict):
        value = spec.get("value")
        return Variable(name, None if value is None else str(value), spec.get("env"), spec.get("prompt"),
                        bool(spec.get("secret", False)))
    return Variable(name, None if spec is None else str(spec))


def _parse_config(cfg: dict) -> Config:
    c = Config()
    for k in ("timeout", "then_timeout"):
        if _is_number(cfg.get(k)):
            setattr(c, k, float(cfg[k]))
    if _is_number(cfg.get("max_actions")):
        c.max_actions = int(cfg["max_actions"])
    if _is_number(cfg.get("type_delay")) and cfg["type_delay"] >= 0:
        c.type_delay = float(cfg["type_delay"])
    intr = cfg.get("interrupts")
    if isinstance(intr, str):
        c.interrupts = Interrupts(mode=intr)
    elif isinstance(intr, dict):
        c.interrupts = Interrupts(mode=intr.get("mode", "report"), allow=list(intr.get("allow") or []))
    if cfg.get("on_failure") in ON_FAILURE:
        c.on_failure = cfg["on_failure"]
    c.reset = list(cfg.get("reset") or [])
    c.model = cfg.get("model")
    for k in ("clear_data_before", "stop_app_after", "strict"):
        if isinstance(cfg.get(k), bool):
            setattr(c, k, cfg[k])
    return c


def _expand(steps: list[dict], cfg: Config, origins: list[_Step]) -> list[Section]:
    ids = [str(s["id"]) for s in steps]
    by_id = {str(s["id"]): s for s in steps}

    def make(a: dict, kind: str, section: str, origin: str) -> Item:
        strict = a.get("strict", cfg.strict)
        it = Item(kind, a[kind], section, origin, strict=bool(strict), wait=float(a.get("wait") or 0),
                  optional=kind == "do" and a.get("optional") is True)
        if kind == "then":
            it.timeout = float(a.get("timeout", cfg.then_timeout))
            it.observe = float(a.get("observe", DEFAULT_OBSERVE))
        return it

    def replay_dos(sec: dict, section: str, stack: tuple[str, ...]) -> list[Item]:
        r = sec.get("replay")
        if not isinstance(r, dict):
            return []
        f, t = ids.index(str(r["from"])), ids.index(str(r["to"]))
        out: list[Item] = []
        for sid in ids[f: t + 1]:
            if sid in stack:
                raise ValueError(f"replay cycle at {sid}")
            src = by_id[sid]
            out += replay_dos(src, section, stack + (sid,))
            out += [make(a, "do", section, sid) for a in src.get("actions") or [] if "do" in a]
        return out

    sections: list[Section] = []
    n = 0
    for sec, origin in zip(steps, origins):
        sid = str(sec["id"])
        items = replay_dos(sec, sid, (sid,))
        items += [make(a, "do" if "do" in a else "then", sid, sid) for a in sec.get("actions") or []]
        for it in items:
            it.index = n
            n += 1
        sections.append(Section(sid, items, on=sec.get("on") if sec.get("on") in PLATFORMS else None,
                                targets=dict(origin.targets)))
    return sections


def load(path: Path) -> Scenario:
    """Load and validate a scenario. Raises ScenarioError if it has errors."""
    issues, r = _check(path)
    if r is None or any(i.level == "error" for i in issues):
        raise ScenarioError(path, issues)
    data = r.data
    cfg = _parse_config(data.get("config") or {})
    variables = {n: parse_variable(n, s) for n, s in (data.get("variables") or {}).items()}
    sections = _expand(data["steps"], cfg, r.steps)
    return Scenario(path=path, name=str(data["name"]), app=data["app"], config=cfg, variables=variables,
                    sections=sections, warnings=[i for i in issues if i.level == "warning"], own_app=r.own_app)


def discover(paths: list[str]) -> list[Path]:
    """Scenario files from files and directories (recursively: *.yaml, *.yml)."""
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(q for q in p.rglob("*") if q.suffix in (".yaml", ".yml") and q.is_file())
        else:
            out.append(p)
    return out


# --------------------------------------------------------------------------- #
# Variables
# --------------------------------------------------------------------------- #


def resolve_variables(sc: Scenario, overrides: dict[str, str], interactive: bool | None = None
                      ) -> tuple[dict[str, str], list[str]]:
    """Return (values, missing). Order: --var, value, env, interactive prompt."""
    if interactive is None:
        interactive = sys.stdin.isatty()
    values: dict[str, str] = {}
    missing: list[str] = []
    for name, var in sc.variables.items():
        if name in overrides:
            values[name] = overrides[name]
        elif var.value is not None:
            values[name] = var.value
        elif var.env and os.environ.get(var.env) is not None:
            values[name] = os.environ[var.env]
        elif interactive:
            msg = (var.prompt or f"Enter value for {name}") + ": "
            values[name] = getpass.getpass(msg) if var.secret else input(msg)
        else:
            missing.append(name)
    return values, missing


def render(text: str, values: dict[str, str], secret_names: set[str]) -> str:
    """Substitute `(name)`. Secret variables stay as `(name)` placeholders (never sent to the AI)."""

    def rep(m: re.Match) -> str:
        name = m.group(1)
        if name in secret_names or name not in values:
            return m.group(0)
        return values[name]

    return VAR_RE.sub(rep, text).replace("\\(", "(").replace("\\)", ")")


def fill_secrets(text: str, values: dict[str, str], secret_names: set[str]) -> str:
    """Replace secret placeholders in text the AI asked to type with the real values."""

    def rep(m: re.Match) -> str:
        name = m.group(1)
        return values[name] if name in secret_names and name in values else m.group(0)

    return VAR_RE.sub(rep, text)
