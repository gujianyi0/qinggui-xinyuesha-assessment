"""Private, quiescent Docker backup and non-destructive restore rehearsal."""
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

from backend.app.config import ROOT
from backend.app.database_transfer import assert_quiescent, assert_same_database
from scripts.docker_live import run_compose


def checked(*args, stdin=None, timeout=180):
    result = run_compose(*args, stdin=stdin, timeout=timeout)
    if result.returncode:
        # Captured command output can contain connection details. Keep it local.
        folder = ROOT / '.local/backups'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'last-command-error.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('Docker operation failed; inspect private backup error log')
    return result.stdout


def fingerprint(database='assessment'):
    code = """import asyncio,json,asyncpg
from sqlalchemy.engine import make_url
from backend.app.config import Settings
from backend.app.database_transfer import fingerprint
async def run():
 c=await asyncpg.connect(make_url(Settings().database_url).set(drivername='postgresql',database=DATABASE).render_as_string(hide_password=False))
 try: print(json.dumps(await fingerprint(c)))
 finally: await c.close()
asyncio.run(run())
""".replace('DATABASE', repr(database))
    return json.loads(checked('run', '--rm', '--no-deps', 'api', 'python', '-c', code))


def label_path(label):
    if not re.fullmatch(r'[a-z0-9-]{1,60}', label):
        raise ValueError('Use a unique lowercase backup label')
    return ROOT / '.local/backups' / label


def relay_running():
    # The supervisor intentionally never accepts on its lock socket. Binding is
    # a non-consuming presence probe; connect() would fill its listen backlog.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 18084))
            return False
        except OSError as error:
            if error.errno in (98, 10013, 10048):
                return True
            raise


def backup(label):
    folder = label_path(label)
    folder.mkdir(parents=True, exist_ok=False)
    relay = ROOT / '.local/public-entry'
    relay_active = relay_running()
    report = {'label': label, 'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Current Docker primary; private data/config remain local', 'passed': False}
    paused = False
    try:
        if relay_active:
            (relay / 'stop').touch()
            deadline = time.monotonic() + 55
            while relay_running():
                if time.monotonic() > deadline:
                    raise TimeoutError('Public relay did not stop; primary backup not started')
                time.sleep(.5)
        # Refuse a busy database before shutdown can cancel a paid run.
        preflight = fingerprint()
        report['preflight_active'] = preflight['active']
        assert_quiescent(preflight)
        # Stop writers before fingerprint/dump. No recovery process starts against this DB.
        paused = True
        checked('stop', 'worker', 'api', 'web')
        source = fingerprint()
        assert_quiescent(source)
        archive = checked('exec', '-T', 'postgres', 'pg_dump', '-U', 'assessment', '-d', 'assessment',
                          '-Fc', '--no-owner', '--no-privileges', timeout=240)
        (folder / 'database.dump').write_bytes(archive)
        (folder / 'fingerprint.json').write_text(json.dumps(source, indent=2), encoding='utf-8')
        hashes = {'database.dump': hashlib.sha256(archive).hexdigest()}
        for name in ('.env.docker-live', '.local/deployment.json', '.local/public-entry/config.json'):
            original = ROOT / name
            if original.exists():
                destination = folder / 'private-config' / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, destination)
                hashes[name] = hashlib.sha256(original.read_bytes()).hexdigest()
        report.update(passed=True, sha256=hashes, database=source)
    finally:
        try:
            if paused:
                checked('up', '-d', '--no-deps', '--wait', '--wait-timeout', '90', 'api', 'worker', 'web')
            if relay_active:
                (relay / 'stop').unlink(missing_ok=True)
                if not relay_running():
                    with (relay / 'supervisor.log').open('ab') as stdout, (relay / 'supervisor-error.log').open('ab') as stderr:
                        subprocess.Popen([sys.executable, '-m', 'scripts.public_service'], cwd=ROOT,
                                         stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                         start_new_session=os.name != 'nt')
            report['service_restart_requested'] = True
        except Exception as error:
            report.update(passed=False, service_restart_error=type(error).__name__)
            raise
        finally:
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            (folder / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'backup': label, 'passed': report['passed'], 'budget': source['budget'],
                      'tables': len(source['tables']), 'archive_sha256': hashes['database.dump']}))


def restore_check(label, database):
    started = time.monotonic()
    folder = label_path(label)
    if not re.fullmatch(r'assessment_restore_[a-z0-9_]{1,40}', database):
        raise ValueError('Restore target must use the isolated assessment_restore_ prefix')
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    archive = folder / 'database.dump'
    if not manifest.get('passed') or hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['sha256']['database.dump']:
        raise ValueError('Backup is incomplete or its archive hash changed')
    for name, expected in manifest['sha256'].items():
        if name == 'database.dump':
            continue
        config = folder / 'private-config' / name
        if not config.is_file() or hashlib.sha256(config.read_bytes()).hexdigest() != expected:
            raise ValueError('Private configuration backup hash changed')
    existing = checked('exec', '-T', 'postgres', 'psql', '-U', 'assessment', '-d', 'assessment', '-At',
                       '-c', f"SELECT count(*) FROM pg_database WHERE datname='{database}'").strip()
    if existing != b'0':
        raise ValueError('Restore target already exists; preserved without overwrite')
    checked('exec', '-T', 'postgres', 'createdb', '-U', 'assessment', database)
    with archive.open('rb') as stream:
        checked('exec', '-T', 'postgres', 'pg_restore', '-U', 'assessment', '-d', database,
                '--no-owner', '--no-privileges', '--exit-on-error', '--single-transaction', stdin=stream, timeout=240)
    target = fingerprint(database)
    assert_same_database(manifest['database'], target)
    evidence = {'passed': True, 'backup': label, 'target': database,
                'archive_sha256': manifest['sha256']['database.dump'],
                'tables': target['tables'], 'budget': target['budget'], 'migration': target['migration'],
                'pgvector': target['pgvector'], 'checked_at': datetime.now(timezone.utc).isoformat(),
                'elapsed_seconds': round(time.monotonic() - started, 3),
                'primary_overwritten': False, 'private_configuration_restored_to_service': False}
    path = ROOT / 'docs/evidence' / f'{label}-restore.json'
    path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'tables': len(target['tables']), 'budget': target['budget'], 'evidence': path.name}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore-check'])
    parser.add_argument('--label', required=True)
    parser.add_argument('--database')
    args = parser.parse_args()
    if args.operation == 'backup':
        backup(args.label)
    else:
        restore_check(args.label, args.database or '')
