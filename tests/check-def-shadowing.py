#!/usr/bin/env python3
"""Regression suite for independent top-level `def` bindings in .n and .ns.

Bootstrap usage:
  python3 tests/check-def-shadowing.py --toolchain out/bootstrap/toolchain \
      --references boot/coreclr/references \
      --report out/bootstrap/reports/def-shadowing.json

A failed test leaves its complete temporary sources and binaries for diagnosis.
Every case is reported in machine-readable JSON as well as stdout.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


@dataclass(frozen=True)
class Case:
    name: str
    mode: str  # module | script
    files: dict[str, str]
    expected: str = ""
    should_compile: bool = True
    diagnostic: str = ""


CASES = [
    Case("local-shadow-capture", "module", {"main.n": """
Run() : void {
  def x = 10;
  def before = () => x;
  def x = "next";
  System.Console.WriteLine(before());
  System.Console.WriteLine(x);
}
Run();
"""}, "10\nnext"),
    Case("module-method-identity", "module", {"main.n": """
def x = 10;
Old() : int { x }
def x = "hello";
New() : string { x }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "10\nhello"),
    Case("module-same-type", "module", {"main.n": """
def x = 1;
Old() : int { x }
def x = x + 9;
New() : int { x }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "1\n10"),
    Case("module-typed-bindings", "module", {"main.n": """
def value : int = 12;
ReadOld() : int { value }
def value : string = "done";
ReadNew() : string { value }
System.Console.WriteLine(ReadOld());
System.Console.WriteLine(ReadNew());
"""}, "12\ndone"),
    Case("module-final-public-export", "module", {
        "defs.n": """
public def x = 10;
public Old() : int { x }
public def x = "hello";
public New() : string { x }
""",
        "main.n": """
using defs;
System.Console.WriteLine(defs.Old());
System.Console.WriteLine(defs.New());
System.Console.WriteLine(defs.x);
"""
    }, "10\nhello\nhello"),
    Case("module-private-then-public", "module", {
        "defs.n": """
def x = 8;
public Old() : int { x }
public def x = "visible";
""",
        "main.n": """
using defs;
System.Console.WriteLine(defs.Old());
System.Console.WriteLine(defs.x);
"""
    }, "8\nvisible"),
    Case("module-top-level-closure", "module", {"main.n": """
def x = 10;
def earlier = () => x;
def x = 20;
System.Console.WriteLine(earlier());
System.Console.WriteLine(x);
"""}, "10\n20"),
    Case("module-tuple-pattern-shadow", "module", {"main.n": """
def (x, y) = (1, 2);
Old() : int { x + y }
def (x, y) = (10, 20);
New() : int { x + y }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "3\n30"),
    Case("module-mutable-remains-shared", "module", {"main.n": """
mutable x = 1;
Read() : int { x }
x = 7;
System.Console.WriteLine(Read());
"""}, "7"),
    Case("module-immutable-assignment-rejected", "module", {"main.n": """
def x = 1;
def x = "immutable";
x = "changed";
"""}, should_compile=False, diagnostic="writable"),
    Case("script-method-identity", "script", {"main.ns": """
def x = 10;
Old() : int { x }
def x = "hello";
New() : string { x }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "10\nhello"),
    Case("script-typed-bindings", "script", {"main.ns": """
def x : int = 9;
Old() : int { x }
def x : string = "typed";
New() : string { x }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "9\ntyped"),
    Case("script-closure-history", "script", {"main.ns": """
def x = 3;
def old = () => x;
def x = 10;
System.Console.WriteLine(old());
System.Console.WriteLine(x);
"""}, "3\n10"),
    Case("script-tuple-pattern-shadow", "script", {"main.ns": """
def (x, y) = (1, 2);
Old() : int { x + y }
def (x, y) = (10, 20);
New() : int { x + y }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "3\n30"),
    Case("script-mutable-tuple-method-write", "script", {"main.ns": """
mutable (x, y) = (0, 0);
Move() : void { x += 10; y += 5 }
Move();
System.Console.WriteLine($"$x, $y");
"""}, "10, 5"),
    Case("script-variant-pattern-shadow", "script", {"main.ns": """
def (Some(x)) = Some(1 : int);
Old() : int { x }
def (Some(x)) = Some(20 : int);
New() : int { x }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "1\n20"),
    Case("script-import-sees-final-binding", "script", {
        "math.ns": """
def x = 2;
Old() : int { x }
def x = "exported";
New() : string { x }
""",
        "main.ns": """
import math;
System.Console.WriteLine(math.Old());
System.Console.WriteLine(math.New());
System.Console.WriteLine(math.x);
"""
    }, "2\nexported\nexported"),
    Case("script-mutable-remains-shared", "script", {"main.ns": """
mutable x : int = 1;
Read() : int { x }
x = 7;
System.Console.WriteLine(Read());
"""}, "7"),
    Case("script-await-shadow", "script", {"main.ns": """
def x = 4;
Old() : int { x }
await System.Threading.Tasks.Task.Yield();
def x = "after";
New() : string { x }
System.Console.WriteLine(Old());
System.Console.WriteLine(New());
"""}, "4\nafter"),
    Case("script-immutable-assignment-rejected", "script", {"main.ns": """
def x = 1;
def x = "immutable";
x = "changed";
"""}, should_compile=False, diagnostic="writable"),
]


def execute(command: list[str], cwd: pathlib.Path, timeout: int = 120) -> dict:
    begun = time.monotonic()
    try:
        process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {"command": command, "returncode": process.returncode,
                "stdout": process.stdout, "stderr": process.stderr,
                "duration_seconds": round(time.monotonic() - begun, 3)}
    except subprocess.TimeoutExpired as exc:
        def stringify(x):
            return x.decode(errors="replace") if isinstance(x, bytes) else (x or "")
        return {"command": command, "returncode": None,
                "stdout": stringify(exc.stdout), "stderr": stringify(exc.stderr) + "\nPROCESS TIMEOUT",
                "duration_seconds": round(time.monotonic() - begun, 3)}
    except OSError as exc:
        return {"command": command, "returncode": None,
                "stdout": "", "stderr": str(exc),
                "duration_seconds": round(time.monotonic() - begun, 3)}


def run_case(case: Case, root: pathlib.Path, toolchain: pathlib.Path,
             references: pathlib.Path) -> dict:
    folder = root / case.name
    folder.mkdir(parents=True)
    for filename, code in case.files.items():
        target = folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code.strip() + "\n", encoding="utf-8")
    entry = folder / ("main.ns" if case.mode == "script" else "main.n")
    outcome = {"name": case.name, "mode": case.mode, "directory": str(folder),
               "expected_output": case.expected, "should_compile": case.should_compile,
               "diagnostic_substring": case.diagnostic}
    if case.mode == "script":
        command = ["dotnet", str(toolchain / "nscript.exe"), "run", str(entry), "--no-cache"]
        run = execute(command, folder)
        combined = run["stdout"] + run["stderr"]
        ok = (run["returncode"] == 0 and run["stdout"].strip() == case.expected.strip()) if case.should_compile else (
            run["returncode"] not in (0, None) and case.diagnostic.lower() in combined.lower())
        outcome.update({"phase": "nscript-run", "run": run, "passed": ok})
        return outcome

    # Compiled .n file module. Source root and entry file are explicit; only the
    # main.n module is the entry point.  All sources are compiled in one call.
    exe = folder / "test.exe"
    all_sources = [entry] + sorted(p for p in folder.rglob("*.n") if p != entry)
    command = ["dotnet", str(toolchain / "ncc.exe"), *map(str, all_sources),
               "-source-root:" + str(folder), "-target-references:" + str(references),
               "-out:" + str(exe), "-launcher-", "-no-color"]
    compile_run = execute(command, folder)
    diagnostics = compile_run["stdout"] + compile_run["stderr"]
    outcome["compile"] = compile_run
    if not case.should_compile:
        outcome.update({"phase": "compile-negative", "passed":
                        compile_run["returncode"] not in (0, None)
                        and case.diagnostic.lower() in diagnostics.lower()})
        return outcome
    if compile_run["returncode"] != 0:
        outcome.update({"phase": "compile", "passed": False})
        return outcome
    config = toolchain / "ncc.runtimeconfig.json"
    if config.exists():
        shutil.copy2(config, folder / "test.runtimeconfig.json")
    else:
        outcome.update({"phase": "setup", "passed": False,
                        "error": f"runtime configuration missing: {config}"})
        return outcome
    for lib in toolchain.glob("Nemerle*.dll"):
        target = folder / lib.name
        if not target.exists(): shutil.copy2(lib, target)
    process = execute(["dotnet", str(exe)], folder)
    outcome.update({"phase": "runtime", "run": process,
                    "passed": process["returncode"] == 0 and process["stdout"].strip() == case.expected.strip()})
    return outcome


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--toolchain", required=True, type=pathlib.Path)
    p.add_argument("--references", required=True, type=pathlib.Path)
    p.add_argument("--report", required=True, type=pathlib.Path)
    p.add_argument("--keep", action="store_true", help="retain temp sources even on success")
    p.add_argument("--filter", default="", help="run only cases containing this substring")
    a = p.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[1]
    toolchain, references = a.toolchain.resolve(), a.references.resolve()
    report = a.report.resolve()
    cases = [c for c in CASES if a.filter.lower() in c.name.lower()]
    if not cases: p.error("no cases selected")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="nemerle-def-shadow-"))
    started = datetime.now(timezone.utc).isoformat()
    results = []
    for i, case in enumerate(cases, 1):
        try:
            result = run_case(case, tmp, toolchain, references)
        except Exception as exc:
            result = {"name": case.name, "mode": case.mode, "phase": "harness",
                      "passed": False, "error": str(exc), "traceback": traceback.format_exc(),
                      "directory": str(tmp / case.name)}
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status}: def-shadowing {i}/{len(cases)} {case.name}", flush=True)
        if not result["passed"]:
            for step in ("compile", "run"):
                if step in result:
                    detail = result[step]
                    print(f"  {step}: exit={detail['returncode']}\n"
                          f"  stdout: {detail['stdout'][-1500:]}\n"
                          f"  stderr: {detail['stderr'][-1500:]}", flush=True)
            if "error" in result: print("  error:", result["error"], flush=True)
    passed = sum(int(r["passed"]) for r in results)
    summary = {"suite": "def-shadowing", "timestamp_utc": started,
               "repo": str(repo), "toolchain": str(toolchain), "references": str(references),
               "count": len(results), "passed": passed, "failed": len(results) - passed,
               "success": passed == len(results), "temporary_directory": str(tmp), "cases": results}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if summary["success"] and not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{'PASS' if summary['success'] else 'FAIL'}: def-shadowing "
          f"{passed}/{len(results)}; report={report}", flush=True)
    if not summary["success"]:
        print(f"Failure artifacts kept: {tmp}", flush=True)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
