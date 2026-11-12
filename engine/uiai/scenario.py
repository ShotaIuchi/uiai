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
PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_-]*){2,}$")
URL_RE = re.compile(r"^https?://", re.I)

PLATFORMS = ("android", "ios", "web")
ON_FAILURE = ("stop_scenario", "next_section", "stop_all")
INTERRUPT_MODES = ("allow", "report", "fail")
CONFIG_KEYS = {
    "timeout", "clear_data_before", "stop_app_after", "strict", "verify",
    "then_timeout", "max_actions", "interrupts", "on_failure", "reset", "model",
}
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


@dataclass
class Scenario:
    path: Path
    name: str
    app: Any
    config: Config
    variables: dict[str, Variable]
    sections: list[Section]
    warnings: list[Issue] = field(default_factory=list)

    @property
    def items(self) -> list[Item]:
        return [it for s in self.sections for it in s.items]

    @property
    def secret_names(self) -> set[str]:
        return {n for n, v in self.variables.items() if v.secret}


# --------------------------------------------------------------------------- #
# YAML loading (with duplicate-key detection for E032)
# --------------------------------------------------------------------------- #


class _Loader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            loader.duplicates.append((key, key_node.start_mark.line + 1))
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


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


def check_data(data: Any, duplicates: list[tuple[Any, int]] | None = None) -> list[Issue]:
    """Validate a parsed scenario. Rule IDs follow skills/scenario-check (E0xx/W0xx)."""
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
    ids: list[str] = []
    for i, sec in enumerate(steps):
        where = f"steps[{i}]"
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

    used_vars: set[str] = set()
    for i, sec in enumerate(steps):
        if not isinstance(sec, dict):
            continue
        where = f"steps[{i}]（{sec.get('id', '')}）"
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
    try:
        data, dups = _read_yaml(path)
    except yaml.YAMLError as e:
        return [Issue("E000", "error", f"YAML の構文エラー: {e}")]
    except OSError as e:
        return [Issue("E000", "error", f"読み込めない: {e}")]
    return check_data(data, dups)


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


def _expand(steps: list[dict], cfg: Config) -> list[Section]:
    ids = [str(s["id"]) for s in steps]
    by_id = {str(s["id"]): s for s in steps}

    def make(a: dict, kind: str, section: str, origin: str) -> Item:
        strict = a.get("strict", cfg.strict)
        it = Item(kind, a[kind], section, origin, strict=bool(strict), wait=float(a.get("wait") or 0))
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
    for sec in steps:
        sid = str(sec["id"])
        items = replay_dos(sec, sid, (sid,))
        items += [make(a, "do" if "do" in a else "then", sid, sid) for a in sec.get("actions") or []]
        for it in items:
            it.index = n
            n += 1
        sections.append(Section(sid, items))
    return sections


def load(path: Path) -> Scenario:
    """Load and validate a scenario. Raises ScenarioError if it has errors."""
    issues = check_file(path)
    if any(i.level == "error" for i in issues):
        raise ScenarioError(path, issues)
    data, _ = _read_yaml(path)
    cfg = _parse_config(data.get("config") or {})
    variables = {n: parse_variable(n, s) for n, s in (data.get("variables") or {}).items()}
    sections = _expand(data["steps"], cfg)
    return Scenario(path=path, name=str(data["name"]), app=data["app"], config=cfg, variables=variables,
                    sections=sections, warnings=[i for i in issues if i.level == "warning"])


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
