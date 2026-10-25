"""
Runs a candidate's `solve` function against one test case in a separate
process. See the module docstring in __init__.py for the honest scope of
this sandbox.
"""

import ast
import json
import subprocess
import sys
from dataclasses import dataclass


TIMEOUT_SECONDS = 5

BLOCKED_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input",
    "globals", "locals", "vars", "exit", "quit", "breakpoint",
}

BLOCKED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "ctypes",
    "multiprocessing", "threading", "importlib", "io", "requests", "urllib",
}


class UnsafeCodeError(ValueError):
    pass


def static_check(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise UnsafeCodeError(f"Syntax error: {exc}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_MODULES:
                    raise UnsafeCodeError(f"Import of '{alias.name}' is not allowed.")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in BLOCKED_MODULES:
                raise UnsafeCodeError(f"Import of '{node.module}' is not allowed.")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise UnsafeCodeError(f"Use of '{node.id}' is not allowed.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            if node.attr not in ("__init__", "__repr__", "__str__", "__eq__", "__lt__", "__len__"):
                raise UnsafeCodeError(f"Access to '{node.attr}' is not allowed.")


_HARNESS = """
import json, sys

{code}

args = json.loads(sys.argv[1])
try:
    result = solve(*args)
except Exception as exc:
    print("###ERROR###" + json.dumps(str(exc)))
    sys.exit(0)

print("###RESULT###" + json.dumps(result))
"""


@dataclass
class RunResult:
    status: str  # ok | wrong_answer | runtime_error | timeout | unsafe
    output: object = None
    error: str | None = None
    runtime_ms: float = 0.0


def run_one(code: str, args: list, expected=None) -> RunResult:
    import time

    try:
        static_check(code)
    except UnsafeCodeError as exc:
        return RunResult(status="unsafe", error=str(exc))

    script = _HARNESS.format(code=code)
    start = time.perf_counter()

    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script, json.dumps(args)],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RunResult(status="timeout", error=f"Exceeded {TIMEOUT_SECONDS}s time limit.")

    elapsed_ms = (time.perf_counter() - start) * 1000
    out = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

    if out.startswith("###ERROR###"):
        return RunResult(status="runtime_error", error=json.loads(out[len("###ERROR###"):]), runtime_ms=elapsed_ms)

    if not out.startswith("###RESULT###"):
        detail = proc.stderr.strip()[-2000:] or "No output produced."
        return RunResult(status="runtime_error", error=detail, runtime_ms=elapsed_ms)

    result = json.loads(out[len("###RESULT###"):])

    if expected is None:
        return RunResult(status="ok", output=result, runtime_ms=elapsed_ms)

    status = "ok" if result == expected else "wrong_answer"
    return RunResult(status=status, output=result, runtime_ms=elapsed_ms)
