#!/usr/bin/env python3
"""Run the scripting chapter's CLI workflows using the source and REPL transcript printed in the book."""
import argparse
import pathlib
import re
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--toolchain', type=pathlib.Path, required=True)
a = p.parse_args()
toolchain = a.toolchain.resolve()
chapter = (pathlib.Path(__file__).resolve().parents[1] / 'doc/book/src/11-scripts.md').read_text()
blocks = re.findall(r'^```nemerle,script\n(.*?)^```', chapter, re.M | re.S)


def named_files(block):
    files = {}
    current = None
    for line in block.splitlines():
        marker = re.fullmatch(r'// file: (.+)', line)
        if marker:
            current = marker[1]
            files[current] = []
        elif current:
            files[current].append(line)
    return {name: '\n'.join(lines) + '\n' for name, lines in files.items()}


with tempfile.TemporaryDirectory(prefix='nemerle script book ') as directory:
    work = pathlib.Path(directory)

    def example(name):
        for index, block in enumerate(blocks):
            files = named_files(block)
            if name not in files:
                continue
            folder = work / f'example{index}'
            folder.mkdir(exist_ok=True)
            for file, text in files.items():
                path = folder / file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return folder / name
        raise AssertionError(f'{name} is missing from the scripting chapter')

    def run(*args, cwd=work, stdin=None, success=True):
        result = subprocess.run(['dotnet', str(toolchain / 'nscript.exe'), '--cache-dir', str(work / 'cache'), *map(str, args)],
                                cwd=cwd, input=stdin, capture_output=True, text=True, timeout=120)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result

    greet = example('greet.ns')
    assert run('run', greet, '--', 'Grace Hopper').stdout.strip() == 'Hello, Grace Hopper!'
    answer = example('answer.ns')
    assert run('run', answer).stdout.strip() == '42'

    # Compile does not run the script. Relocating the whole saved set needs neither original source nor child files.
    for source, expected in [(greet, 'Hello, Ada!'), (example('use_counter.ns'), 'counter ready\n1\n2')]:
        artifact = work / (source.stem + '.dll')
        assert run('compile', source, artifact).stdout.strip() == ''
        relocated = work / ('relocated-' + source.stem)
        relocated.mkdir()
        shutil.copy2(artifact, relocated / artifact.name)
        descriptor = pathlib.Path(str(artifact) + '.script')
        shutil.copy2(descriptor, relocated / descriptor.name)
        dependencies = pathlib.Path(str(artifact) + '.dependencies')
        if dependencies.exists():
            shutil.copytree(dependencies, relocated / dependencies.name)
        assert run('run-compiled', relocated / artifact.name, '--', 'Ada', cwd=relocated).stdout.strip() == expected

    # The transcript itself supplies both the entered commands and expected values.
    repl = chapter.split('## Interactive use: the REPL\n', 1)[1]
    transcript = re.search(r'^```text\n(.*?)^```', repl, re.M | re.S)[1]
    commands, expected = [], []
    for line in transcript.splitlines():
        if line.startswith(('>>> ', '... ')):
            commands.append(line[4:])
        elif line.strip():
            expected.append(line)
    history = work / 'experiment.history'
    first = run('repl', '--history', history, stdin='\n'.join(commands) + '\n')
    assert first.stdout.strip().splitlines() == expected, first.stdout + first.stderr
    inspected = run('repl', '--history', history, stdin=':history\n:quit\n')
    assert '0: 40 : int' in inspected.stdout and not any(line in ('40', '42') for line in inspected.stdout.splitlines()), inspected.stdout
    replayed = run('repl', '--history', history, stdin=':replay\n:quit\n')
    assert replayed.stdout.strip().splitlines() == expected, replayed.stdout + replayed.stderr

    # Ordinary data paths use cwd; compilation failures do not execute earlier top-level statements.
    data_script = work / 'elsewhere/read.ns'
    data_script.parent.mkdir()
    data_script.write_text('System.Console.WriteLine(System.IO.File.ReadAllText("input.txt"))\n')
    (work / 'input.txt').write_text('current directory')
    (data_script.parent / 'input.txt').write_text('script directory')
    assert run('run', data_script).stdout.strip() == 'current directory'
    broken = work / 'broken.ns'
    broken.write_text('System.Console.WriteLine("must not execute");\ndef n = "text" * 2;\nn\n')
    failed = run('run', broken, success=False)
    assert not failed.stdout.strip() and 'broken.ns' in failed.stderr, failed.stdout + failed.stderr

print('PASS: book arguments/results, compiled artifact relocation/imports, REPL transcript/history/replay, data paths and error behavior')
