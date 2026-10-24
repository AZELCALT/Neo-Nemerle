#!/usr/bin/env python3
"""Measure one large method with fixed-type or changing-type untyped mutable locals."""
import argparse
import json
import pathlib
import subprocess
import tempfile
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain', type=pathlib.Path, required=True)
p.add_argument('--counts', type=int, nargs='+', default=[100, 500, 1000])
p.add_argument('--timeout', type=float, default=90)
p.add_argument('--report', type=pathlib.Path, required=True)
a = p.parse_args()
toolchain = a.toolchain.resolve()
work = pathlib.Path(tempfile.mkdtemp(prefix='nemerle-flow-scaling-'))
report = {'toolchain': str(toolchain), 'artifacts': str(work), 'cases': []}
print('Type flow benchmark artifacts:', work, flush=True)
for count in a.counts:
    for changing in (False, True):
        name = 'changing' if changing else 'fixed'
        source = work / ('case_%d_%s.n' % (count, name))
        lines = ['Run() : void {']
        for i in range(count):
            lines.extend(['mutable x%d = 1;' % i, 'x%d = %s;' % (i, '"text"' if changing else '2')])
        lines.extend(['System.Console.WriteLine("ok");', '}', 'Run()'])
        source.write_text('\n'.join(lines) + '\n')
        command = [str(toolchain / 'ncc'), str(source), '-source-root:' + str(work),
                   '-out:' + str(source.with_suffix('.exe')), '-launcher-', '-no-color']
        row = {'locals': count, 'types': name, 'command': command}
        start = time.perf_counter()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=a.timeout)
            row.update(seconds=round(time.perf_counter() - start, 3), exit_code=result.returncode)
            source.with_suffix('.log').write_text(result.stdout + result.stderr)
        except subprocess.TimeoutExpired:
            row.update(timeout_seconds=a.timeout)
        report['cases'].append(row)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(row), flush=True)
