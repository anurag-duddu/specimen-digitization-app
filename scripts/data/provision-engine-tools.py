#!/usr/bin/env python3
"""Provision only the three approved engine assets; no package manager or execution.

CI calls --download explicitly after selecting a normal cache restore or a NEW
cold directory. Wrappers use --verify-only and never download missing tools.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('engine_gate', ROOT / 'scripts/ci/engine_contract_gate.py')
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)
FILENAMES = {'dataconnect': 'dataconnect-emulator-3.2.0',
             'storage': 'cloud-storage-rules-runtime-v1.1.3.jar', 'firebase': 'firebase-tools-linux'}
VARIABLES = {'dataconnect': 'DATACONNECT_EMULATOR_BIN', 'storage': 'STORAGE_RULES_RUNTIME_JAR', 'firebase': 'FIREBASE_CLI_BIN'}


def verify_asset(path, approved, *, version):
    gate.require(approved['version'] == version, 'asset version mismatch')
    path = gate.regular_file(path)
    gate.require(path.stat().st_size == approved['bytes'], f'asset size mismatch: {path}')
    gate.require(gate.file_hash(path) == approved['sha256'], f'asset hash mismatch: {path}')
    return {'path': str(path), **{key: approved[key] for key in ('version', 'bytes', 'sha256')}}


def download_asset(path, approved, *, opener=urllib.request.urlopen):
    """Bound even chunked responses; publish only fully verified bytes."""
    path = Path(path)
    gate.require(not path.exists() and not path.is_symlink(), 'refuse replacing cached asset')
    temporary = path.with_name(path.name + '.partial')
    try:
        with opener(approved['url']) as source, temporary.open('xb') as target:
            total = 0
            while block := source.read(1024 * 1024):
                total += len(block)
                gate.require(total <= approved['bytes'], 'download size exceeds pin')
                target.write(block)
            target.flush()
            os.fsync(target.fileno())
        verify_asset(temporary, approved, version=approved['version'])
        os.chmod(temporary, 0o600 if path.suffix == '.jar' else 0o700)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_directory(directory, *, mode, event, restore):
    directory = Path(directory).absolute()
    gate.require(mode in ('normal', 'cold'), 'unknown cache mode')
    fresh = not directory.exists() and not directory.is_symlink()
    if mode == 'cold':
        gate.require(event == 'workflow_dispatch', 'cold cache is dispatch-only')
        gate.require(restore == 'bypassed', 'cold restore must be bypassed')
        gate.require(fresh, 'cold requires a new nonexistent directory, even if empty')
    else:
        gate.require(restore in ('hit', 'miss'), 'normal restore must be hit or miss')
    for part in (directory, *directory.parents):
        gate.require(not part.is_symlink(), f'symlinked cache directory: {part}')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    gate.require(directory.is_dir(), 'cache must be a directory')
    entries = len(list(directory.iterdir()))
    gate.require(restore != 'hit' or entries > 0, 'empty restored cache')
    gate.require(restore != 'miss' or entries == 0, 'cache miss contains inherited files')
    os.chmod(directory, 0o700)
    return {'mode': mode, 'directory_private': True, 'directory_fresh': fresh,
            'entries_before': entries, 'restore': restore}


def load_toolchain():
    config = gate.read_json(ROOT / 'scripts/data/engine-toolchain.json')
    gate.require(config == gate.APPROVED_TOOLCHAIN, 'unapproved toolchain version or bytes')
    return config


def verify_directory(directory, config):
    directory = Path(directory).absolute()
    gate.require(stat.S_IMODE(directory.stat().st_mode) == 0o700, 'engine directory must be private')
    gate.require(sorted(p.name for p in directory.iterdir()) == sorted(FILENAMES.values()), 'missing or unexpected cache files')
    return {name: verify_asset(directory / FILENAMES[name], pin, version=gate.APPROVED_TOOLCHAIN['assets'][name]['version'])
            for name, pin in config['assets'].items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--mode', choices=('normal', 'cold'), default=os.environ.get('ENGINE_CACHE_MODE', 'normal'))
    parser.add_argument('--restore', choices=('hit', 'miss', 'bypassed'))
    parser.add_argument('--output', type=Path, required=True, help='private provenance JSON outside the cached directory')
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument('--download', action='store_true')
    exclusive.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = load_toolchain()
        directory = args.directory.absolute()
        gate.require(not args.output.absolute().is_relative_to(directory), 'report must be outside cached engine files')
        if args.verify_only:
            evidence = gate.read_json(args.output)
            gate.require(evidence['directory'] == str(directory) and evidence['toolchain_digest'] == gate.file_hash(ROOT / 'scripts/data/engine-toolchain.json'), 'cache provenance mismatch')
            cache = evidence['cache']
            gate.require(cache['mode'] == args.mode, 'cache mode mismatch')
        else:
            if args.download:
                gate.require(os.environ.get('GITHUB_ACTIONS') == 'true' and platform.system() == 'Linux' and platform.machine() == 'x86_64', 'downloads are hosted Linux AMD64 only; no local downloads')
            cache = prepare_directory(directory, mode=args.mode, event=os.environ.get('GITHUB_EVENT_NAME'), restore=args.restore)
            # Refuse a corrupt/partial restore before considering ANY download.
            allowed = set(FILENAMES.values())
            gate.require(all(p.name in allowed for p in directory.iterdir()), 'unexpected or partial cache file')
            for name, pin in config['assets'].items():
                path = directory / FILENAMES[name]
                if path.exists() or path.is_symlink():
                    verify_asset(path, pin, version=pin['version'])
                else:
                    gate.require(args.restore != 'hit' and args.download, f'missing restored asset: {name}')
                    download_asset(path, pin)
            evidence = {'directory': str(directory), 'toolchain_digest': gate.file_hash(ROOT / 'scripts/data/engine-toolchain.json'), 'cache': cache}
        tools = verify_directory(directory, config)
        if args.verify_only:
            # The wrapper cannot execute a caller-selected substitute path.
            for name, variable in VARIABLES.items():
                gate.require(os.environ.get(variable) == tools[name]['path'], f'engine path mismatch: {variable}')
            inspection = gate.inspect_tools(os.environ)
            gate.require(inspection['tools'] == tools, 'runtime/tool preflight mismatch')
            runtime = inspection['runtime']
            gate.require(evidence.get('runtime') == runtime, 'recorded runtime differs from provisioning observations')
        else:
            runtime = gate.inspect_runtime(os.environ)
            evidence['runtime'] = runtime
            gate.atomic_json(args.output, evidence)
        print(json.dumps({'tools': tools, 'runtime': runtime, 'cache': cache}, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f'engine provisioning: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
