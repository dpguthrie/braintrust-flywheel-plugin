#!/usr/bin/env python3
"""Deterministic fake `bt` CLI for bt-flywheel offline harness scenarios."""

import json
import os
import sys
import time
from pathlib import Path


def _load_fixture():
    fixture_path = os.getenv("FAKE_BT_FIXTURE")
    if not fixture_path:
        return {}
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _log_command(argv):
    log_path = os.getenv("FAKE_BT_COMMAND_LOG")
    if not log_path:
        return
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "argv": argv,
        "command": "bt " + " ".join(argv),
    }
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _matches(route, argv):
    command = " ".join(argv).lower()
    prefix = route.get("argv_prefix")
    if prefix and argv[: len(prefix)] != prefix:
        return False

    for term in _as_list(route.get("contains")):
        if str(term).lower() not in command:
            return False

    for term in _as_list(route.get("not_contains")):
        if str(term).lower() in command:
            return False

    return True


def _emit(route):
    if route.get("stderr"):
        print(route["stderr"], file=sys.stderr)
    if "stdout_json" in route:
        print(json.dumps(route["stdout_json"], indent=2, sort_keys=True))
    elif "stdout" in route:
        print(route["stdout"])
    return int(route.get("exit_code", 0))


def main():
    argv = sys.argv[1:]
    _log_command(argv)

    fixture = _load_fixture()
    routes = fixture.get("bt", {}).get("routes", [])
    for route in routes:
        if _matches(route, argv):
            return _emit(route)

    strict = os.getenv("FAKE_BT_STRICT", "1") != "0"
    if strict:
        print(
            "Unexpected fake bt command: bt " + " ".join(argv),
            file=sys.stderr,
        )
        return 17

    fallback = fixture.get("bt", {}).get("fallback", {})
    if fallback:
        return _emit(fallback)
    print(json.dumps({"rows": [], "note": "fake bt fallback"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
