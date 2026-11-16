"""Reproduce host-only checks and record exact logs without importing devices.

Run from any directory: python pi_hmi/tests/run_host_checks.py
Outputs go to build/m7-evidence, never to production paths. Optional --root-app
checks the preserved, untracked protocol-1 app separately when it exists.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(output, include_root=False):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')

    def check(name, args, cwd):
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=180)
        text = result.stdout + result.stderr
        log = output / (name + '.txt')
        log.write_text(text, encoding='utf-8', newline='\n')
        results.append(dict(name=name, command=args, cwd=str(cwd.relative_to(ROOT)) or '.',
                            exit_code=result.returncode, log=log.name,
                            log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        print(f'{name}: {"PASS" if result.returncode == 0 else "FAIL"}', flush=True)

    pi = ROOT / 'pi_hmi'
    check('existing-integration', [sys.executable, 'check_integration.py'], pi)
    check('phase0-contracts', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phase0.py', '-v'], pi)
    check('m0-contracts', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m0.py', '-v'], pi)
    check('m1-state-permissions', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m1.py', '-v'], pi)
    check('m1-http-boundary', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m1_http.py', '-v'], pi)
    check('m2-sqlite-recovery', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m2.py', '-v'], pi)
    check('m3-durable-events', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m3.py', '-v'], pi)
    check('m4-grow-hmi', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m4.py', '-v'], pi)
    check('m5-camera-ml', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m5.py', '-v'], pi)
    check('m5-clock-recovery', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m5_clock.py', '-v'], pi)
    check('m6-history-export', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m6.py', '-v'], pi)
    check('m7-storage-backup', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_m7.py', '-v'], pi)
    if include_root:
        check('preserved-root-app', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], ROOT)
    parsed = sorted(pi.rglob('*.py'))
    parsed = [p for p in parsed if not any(x in ('venv', '.venv', '__pycache__') for x in p.relative_to(pi).parts)]
    for path in parsed:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    results.append(dict(name='python-parse', files=len(parsed), exit_code=0))
    node = shutil.which('node')
    if node:
        check('javascript-parse', [node, '--check', 'static/hmi.js'], pi)
        check('history-javascript-parse', [node, '--check', 'static/history.js'], pi)
        check('storage-javascript-parse', [node, '--check', 'static/storage.js'], pi)
    else:
        results.append(dict(name='javascript-parse', skipped='node not available'))
    compiler = shutil.which('g++')
    if compiler:
        binary = output / ('firmware-test.exe' if os.name == 'nt' else 'firmware-test')
        check('firmware-compile', [compiler, '-std=c++11', 'tests/firmware_behavior.cpp', '-o', str(binary)], pi)
        if results[-1]['exit_code'] == 0:
            check('firmware-behavior', [str(binary)], pi)
    else:
        results.append(dict(name='firmware-behavior', skipped='g++ unavailable locally; required CI job compiles/runs actual sketch harness'))
    source_files = sorted({p for folder in (pi, ROOT / 'docs/phase0') for p in folder.rglob('*')
                           if p.is_file() and p.suffix in ('.py', '.ino', '.json', '.sql', '.js', '.cjs', '.html', '.css', '.cpp')
                           and not any(x in ('.venv', 'venv', '__pycache__') for x in p.relative_to(ROOT).parts)})
    versions = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], capture_output=True, text=True, env=env, check=True).stdout
    (output / 'host-packages.txt').write_text(versions, encoding='utf-8', newline='\n')
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                  platform=sys.platform, commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  scope='Host/synthetic only; no devices, deployment, flash, production restart or physical acceptance',
                  results=results, source_sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files})
    (output / 'HOST_TEST_RESULTS.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return any(r.get('exit_code', 0) != 0 for r in results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/m7-evidence')
    parser.add_argument('--root-app', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args.output.resolve(), args.root_app))
