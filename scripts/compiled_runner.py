#!/usr/bin/env python3
"""Compiled scenario runner for uiai.

Executes compiled JSON IR deterministically using ADB commands,
without requiring AI inference for most steps.

Usage:
    python scripts/compiled_runner.py <compiled.json> [options]

Options:
    --device <serial>     ADB device serial
    --output-dir <path>   Output directory for results
    --skip-ai             Skip AI checkpoint steps (mark as skipped)
    --variables KEY=VAL   Override variables (repeatable)
    --recompile           Force recompilation from source YAML
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from backends.adb_backend import ADBBackend, ADBError
from utils.uitree_parser import (
    find_by_text,
    find_edit_text,
    parse_uitree,
    resolve_element,
    text_exists,
)


class CompiledRunnerError(Exception):
    """Raised when the compiled runner encounters an error."""


class CompiledRunner:
    """Executes a compiled JSON IR scenario."""

    def __init__(
        self,
        compiled_path: str,
        device: str | None = None,
        output_dir: str | None = None,
        skip_ai: bool = False,
        variable_overrides: dict | None = None,
    ):
        self.compiled_path = compiled_path
        self.skip_ai = skip_ai
        self.variable_overrides = variable_overrides or {}

        with open(compiled_path, "r", encoding="utf-8") as f:
            self.compiled = json.load(f)

        self.adb = ADBBackend(device)
        self.output_dir = output_dir or self._default_output_dir()
        self.variables = self._resolve_variables()
        self.results: list[dict] = []
        self.start_time: str = ""

    def _default_output_dir(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        source = Path(self.compiled.get("source", "compiled")).stem
        return f".adb-test/results/{ts}/{source}"

    def _resolve_variables(self) -> dict:
        """Resolve variables from compiled.json + overrides."""
        variables = dict(self.compiled.get("variables", {}))
        variables.update(self.variable_overrides)
        return variables

    def _interpolate(self, text: str) -> str:
        """Replace (variable_name) with resolved values."""
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in self.variables:
                val = self.variables[var_name]
                return val if val is not None else ""
            return match.group(0)

        return re.sub(r"(?<!\\)\(([a-zA-Z_][a-zA-Z0-9_]*)\)", replacer, text)

    def check_staleness(self) -> bool:
        """Check if compiled.json is stale (source YAML changed)."""
        source_path = self.compiled.get("source", "")
        expected_hash = self.compiled.get("source_hash", "")

        if not source_path or not os.path.exists(source_path):
            return False

        with open(source_path, "rb") as f:
            actual_hash = "sha256:" + hashlib.sha256(f.read()).hexdigest()

        if expected_hash and actual_hash != expected_hash:
            print(
                f"WARNING: Source YAML has changed since compilation.\n"
                f"  Expected: {expected_hash}\n"
                f"  Actual:   {actual_hash}\n"
                f"  Consider recompiling with --recompile"
            )
            return True
        return False

    def run(self) -> dict:
        """Execute all compiled steps."""
        os.makedirs(self.output_dir, exist_ok=True)

        if not self.adb.check_connection():
            raise CompiledRunnerError("No ADB device connected")

        self.adb.get_screen_size()
        self.check_staleness()

        self.start_time = datetime.now(timezone.utc).isoformat()
        steps = self.compiled.get("steps", [])

        print(f"Running compiled scenario: {self.compiled.get('source', '?')}")
        print(f"Steps: {len(steps)}, Device: {self.adb.device_serial or 'default'}")
        print(f"Output: {self.output_dir}")
        print()

        for step in steps:
            self._execute_step(step)

        end_time = datetime.now(timezone.utc).isoformat()
        result = self._build_result(end_time)

        result_path = os.path.join(self.output_dir, "result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self._print_summary(result)
        return result

    def _execute_step(self, step: dict) -> None:
        """Execute a single compiled step."""
        idx = step.get("index", 0)
        section = step.get("section", "")
        step_type = step.get("type", "")
        original = step.get("original", "")
        compiled = step.get("compiled", {})
        strategy = compiled.get("strategy", "")
        wait_sec = step.get("wait", 0)

        prefix = f"[{idx:02d}] {section}"
        print(f"{prefix}: {original}")

        step_result = {
            "index": idx,
            "section": section,
            "action_type": step_type,
            "action": original,
            "strict": step.get("strict", False),
            "status": "passed",
            "execution": {"method": "compiled", "strategy": strategy},
            "evidence": {},
        }

        try:
            # Capture before screenshot
            before_path = os.path.join(
                self.output_dir, f"step_{idx:02d}_before.png"
            )
            self.adb.screenshot(before_path)
            step_result["evidence"]["screenshot_before"] = os.path.basename(
                before_path
            )

            # Capture UITree
            uitree_path = os.path.join(
                self.output_dir, f"step_{idx:02d}_uitree.xml"
            )
            xml_content = self.adb.save_uitree(uitree_path)
            step_result["evidence"]["uitree"] = os.path.basename(uitree_path)

            # Execute strategy
            if step_type == "do":
                self._execute_do(compiled, xml_content, step_result)
            elif step_type == "then":
                self._execute_then(compiled, xml_content, step_result)
            elif step_type == "replay":
                self._execute_replay(compiled, step_result)

            # Wait if specified
            if wait_sec > 0:
                self.adb.wait(wait_sec)

            # Capture after screenshot
            after_path = os.path.join(
                self.output_dir, f"step_{idx:02d}_after.png"
            )
            self.adb.screenshot(after_path)
            step_result["evidence"]["screenshot_after"] = os.path.basename(
                after_path
            )

            status_icon = {
                "passed": "OK",
                "skipped": "SKIP",
                "failed": "FAIL",
                "ai_required": "AI",
            }.get(step_result["status"], "?")
            print(f"  -> {status_icon} ({strategy})")

        except ADBError as e:
            step_result["status"] = "failed"
            step_result["execution"]["error"] = str(e)
            print(f"  -> FAIL: {e}")
        except Exception as e:
            step_result["status"] = "failed"
            step_result["execution"]["error"] = str(e)
            print(f"  -> ERROR: {e}")

        self.results.append(step_result)

    def _execute_do(
        self, compiled: dict, xml_content: str, step_result: dict
    ) -> None:
        """Execute a 'do' action strategy."""
        strategy = compiled.get("strategy", "")

        if strategy == "app_launch":
            package = self._interpolate(compiled["package"])
            self.adb.launch_app(package)

        elif strategy == "app_stop":
            package = self._interpolate(compiled["package"])
            self.adb.stop_app(package)

        elif strategy == "app_restart":
            package = self._interpolate(compiled["package"])
            self.adb.stop_app(package)
            self.adb.wait(1)
            self.adb.launch_app(package)

        elif strategy == "tap_by_text":
            root = parse_uitree(xml_content)
            search_text = self._interpolate(compiled.get("search_text", ""))
            elem = resolve_element(root, compiled)
            if elem:
                self.adb.tap(elem.center_x, elem.center_y)
                step_result["target_element"] = {
                    "text": elem.text,
                    "resource_id": elem.resource_id,
                    "bounds": elem.bounds,
                    "center": [elem.center_x, elem.center_y],
                }
            else:
                step_result["status"] = "ai_required"
                step_result["execution"]["error"] = (
                    f"Element not found: {search_text}"
                )

        elif strategy == "tap_by_resource_id":
            root = parse_uitree(xml_content)
            elem = resolve_element(root, compiled)
            if elem:
                self.adb.tap(elem.center_x, elem.center_y)
                step_result["target_element"] = {
                    "text": elem.text,
                    "resource_id": elem.resource_id,
                    "bounds": elem.bounds,
                    "center": [elem.center_x, elem.center_y],
                }
            else:
                step_result["status"] = "ai_required"
                step_result["execution"]["error"] = (
                    f"Element not found by resource-id: "
                    f"{compiled.get('resource_id', '')}"
                )

        elif strategy == "text_input":
            root = parse_uitree(xml_content)
            input_text = self._interpolate(compiled.get("input_text", ""))
            field_hint = self._interpolate(compiled.get("field_hint", ""))

            # Try to find the EditText
            metadata = compiled.get("element_metadata")
            elem = None
            if metadata and metadata.get("resource_id"):
                from utils.uitree_parser import find_by_resource_id
                elem = find_by_resource_id(root, metadata["resource_id"])
            if not elem:
                elem = find_edit_text(root, field_hint)

            if elem:
                self.adb.tap(elem.center_x, elem.center_y)
                self.adb.wait(0.3)
                # Clear existing text
                self.adb.keyevent(123)  # MOVE_END
                for _ in range(100):
                    self.adb.keyevent(67)  # DEL
                self.adb.input_text(input_text)
            else:
                step_result["status"] = "ai_required"
                step_result["execution"]["error"] = (
                    f"EditText not found for: {field_hint}"
                )

        elif strategy == "scroll_fixed":
            direction = compiled.get("direction", "down")
            distance = compiled.get("distance", 500)
            duration_ms = compiled.get("duration_ms", 300)
            self.adb.scroll(direction, distance, duration_ms)

        elif strategy == "scroll_to_find":
            root = parse_uitree(xml_content)
            search_text = self._interpolate(
                compiled.get("search_text", "")
            )
            direction = compiled.get("direction", "down")
            max_scrolls = compiled.get("max_scrolls", 10)
            distance = compiled.get("distance", 500)
            duration_ms = compiled.get("duration_ms", 300)

            found = text_exists(root, search_text)
            attempts = 0
            while not found and attempts < max_scrolls:
                self.adb.scroll(direction, distance, duration_ms)
                self.adb.wait(0.5)
                xml_content = self.adb.dump_uitree()
                root = parse_uitree(xml_content)
                found = text_exists(root, search_text)
                attempts += 1

            if not found:
                step_result["status"] = "ai_required"
                step_result["execution"]["error"] = (
                    f"Text '{search_text}' not found after "
                    f"{max_scrolls} scrolls"
                )

        elif strategy == "keyevent":
            keycode = compiled.get("keycode", 4)
            self.adb.keyevent(keycode)

        elif strategy == "wait":
            duration = compiled.get("duration_sec", 1)
            self.adb.wait(duration)

        elif strategy == "ai_checkpoint":
            if self.skip_ai:
                step_result["status"] = "skipped"
                step_result["execution"]["reason"] = "AI skipped (--skip-ai)"
            else:
                step_result["status"] = "ai_required"
                step_result["execution"]["reason"] = (
                    "AI inference required for this step"
                )

        else:
            step_result["status"] = "failed"
            step_result["execution"]["error"] = (
                f"Unknown strategy: {strategy}"
            )

    def _execute_then(
        self, compiled: dict, xml_content: str, step_result: dict
    ) -> None:
        """Execute a 'then' assertion strategy."""
        strategy = compiled.get("strategy", "")

        if strategy == "strict_text_match":
            root = parse_uitree(xml_content)
            search_text = self._interpolate(
                compiled.get("search_text", "")
            )
            match_type = compiled.get("match_type", "exact")
            negate = compiled.get("negate", False)

            found = text_exists(root, search_text, match_type)

            if negate:
                if found:
                    step_result["status"] = "failed"
                    step_result["verification"] = {
                        "method": "strict_match",
                        "result": "failed",
                        "reason": f"Text '{search_text}' was found but should not be present",
                    }
                else:
                    step_result["verification"] = {
                        "method": "strict_match",
                        "result": "passed",
                        "reason": f"Text '{search_text}' correctly not found",
                    }
            else:
                if found:
                    step_result["verification"] = {
                        "method": "strict_match",
                        "result": "passed",
                        "reason": f"Text '{search_text}' found in UITree",
                    }
                else:
                    step_result["status"] = "failed"
                    step_result["verification"] = {
                        "method": "strict_match",
                        "result": "failed",
                        "reason": f"Text '{search_text}' not found in UITree",
                    }

        elif strategy == "ai_checkpoint":
            if self.skip_ai:
                step_result["status"] = "skipped"
                step_result["verification"] = {
                    "method": "skipped",
                    "result": "skipped",
                    "reason": "AI skipped (--skip-ai)",
                }
            else:
                step_result["status"] = "ai_required"
                step_result["verification"] = {
                    "method": "ai_required",
                    "result": "ai_required",
                    "reason": "AI Vision evaluation required",
                }

        else:
            step_result["status"] = "failed"
            step_result["verification"] = {
                "method": "unknown",
                "result": "failed",
                "reason": f"Unknown then strategy: {strategy}",
            }

    def _execute_replay(self, compiled: dict, step_result: dict) -> None:
        """Execute replay steps."""
        expanded = compiled.get("expanded_steps", [])
        replayed = []
        for sub_step in expanded:
            sub_compiled = sub_step.get("compiled", {})
            sub_strategy = sub_compiled.get("strategy", "")

            xml_content = self.adb.dump_uitree()
            sub_result = {"status": "passed"}
            self._execute_do(sub_compiled, xml_content, sub_result)

            replayed.append({
                "section": sub_step.get("section", ""),
                "do": sub_step.get("original", ""),
                "status": sub_result["status"],
            })

        step_result["replayed_steps"] = replayed
        if any(r["status"] != "passed" for r in replayed):
            step_result["status"] = "failed"

    def _build_result(self, end_time: str) -> dict:
        """Build the final result.json."""
        passed = sum(1 for r in self.results if r["status"] == "passed")
        failed = sum(1 for r in self.results if r["status"] == "failed")
        skipped = sum(1 for r in self.results if r["status"] == "skipped")
        ai_required = sum(
            1 for r in self.results if r["status"] == "ai_required"
        )
        total = len(self.results)

        return {
            "scenario": {
                "name": Path(self.compiled.get("source", "")).stem,
                "file": self.compiled.get("source", ""),
                "compiled": True,
                "compiled_from": self.compiled_path,
            },
            "device": {
                "serial": self.adb.device_serial or "default",
                "screen_size": f"{self.adb.screen_width}x{self.adb.screen_height}",
            },
            "execution": {
                "start_time": self.start_time,
                "end_time": end_time,
                "mode": "compiled",
            },
            "summary": {
                "total_steps": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "ai_required": ai_required,
                "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            },
            "steps": self.results,
            "output_dir": self.output_dir,
        }

    def _print_summary(self, result: dict) -> None:
        """Print execution summary."""
        summary = result["summary"]
        print()
        print("=" * 50)
        print("Compiled Execution Complete")
        print("=" * 50)
        print()
        print(f"Total Steps:  {summary['total_steps']}")
        print(f"Passed:       {summary['passed']}")
        print(f"Failed:       {summary['failed']}")
        print(f"Skipped:      {summary['skipped']}")
        print(f"AI Required:  {summary['ai_required']}")
        print(f"Pass Rate:    {summary['pass_rate']}%")
        print()
        print(f"Results: {os.path.join(self.output_dir, 'result.json')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute a compiled uiai scenario"
    )
    parser.add_argument(
        "compiled_json", help="Path to compiled.json"
    )
    parser.add_argument(
        "--device", "-d", help="ADB device serial"
    )
    parser.add_argument(
        "--output-dir", "-o", help="Output directory"
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI checkpoint steps",
    )
    parser.add_argument(
        "--variables",
        "-v",
        action="append",
        default=[],
        help="Override variable (KEY=VALUE, repeatable)",
    )
    args = parser.parse_args()

    var_overrides = {}
    for v in args.variables:
        if "=" in v:
            key, val = v.split("=", 1)
            var_overrides[key] = val

    runner = CompiledRunner(
        compiled_path=args.compiled_json,
        device=args.device,
        output_dir=args.output_dir,
        skip_ai=args.skip_ai,
        variable_overrides=var_overrides,
    )

    try:
        result = runner.run()
        sys.exit(0 if result["summary"]["failed"] == 0 else 1)
    except CompiledRunnerError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except ADBError as e:
        print(f"ADB Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
