"""Start a local paid evaluation API, bounded by a grant in the primary ledger."""
import argparse
import json
import os
import re
import subprocess

from dotenv import dotenv_values

from backend.app.config import ROOT
from scripts.backup_docker_primary import checked
from scripts.docker_live import PROJECT, docker_command, docker_environment

DATABASE = 'assessment_eval_v19'
CONTAINER = 'qinggui-assessment-eval-v19'
ENV_FILE = ROOT / '.local/v19-evaluation.env'


def docker(*args, timeout=180):
    result = subprocess.run([docker_command(), *args], cwd=ROOT, env=docker_environment(),
                            capture_output=True, timeout=timeout)
    if result.returncode:
        (ROOT / '.local/v19-evaluation-command-error.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('Isolated Docker command failed; private log preserved')
    return result.stdout


def setup(resume_empty=False):
    private = dotenv_values(ROOT / '.env.docker-live', interpolate=False)
    existing = checked('exec', '-T', 'postgres', 'psql', '-U', 'assessment', '-d', 'assessment', '-At',
                       '-c', f"SELECT count(*) FROM pg_database WHERE datname='{DATABASE}'").strip()
    if existing != b'0' or ENV_FILE.exists():
        empty = checked('exec', '-T', 'postgres', 'psql', '-U', 'assessment', '-d', DATABASE, '-At',
                        '-c', "SELECT count(*) FROM pg_tables WHERE schemaname='public'").strip()
        if not resume_empty or empty != b'0':
            raise ValueError('Isolated evaluation already exists; never reset its ledger. Resume the existing container.')
    from sqlalchemy import URL
    url = URL.create('postgresql+asyncpg', username='assessment', password=private['POSTGRES_PASSWORD'],
                     host='postgres', port=5432, database=DATABASE)
    private.update(DATABASE_URL=url.render_as_string(hide_password=False), TOTAL_BUDGET_CNY='30',
                   BUDGET_WARNING_CNY='25', ENABLE_TEST_FAULTS='true', CREATE_SCHEMA='false',
                   MODEL_CONCURRENCY='1', REDIS_URL='redis://127.0.0.1:1/0', SEED_USERS='true')
    # Docker --env-file reads literal values (unlike dotenv, it keeps quote characters).
    if any('\n' in str(value) or '\r' in str(value) for value in private.values() if value is not None):
        raise ValueError('Multiline environment values are unsupported')
    ENV_FILE.write_text(''.join(f'{key}={value}\n' for key, value in private.items()
                                if value is not None), encoding='utf-8')
    if existing == b'0':
        checked('exec', '-T', 'postgres', 'createdb', '-U', 'assessment', DATABASE)
    common = ['--network', f'{PROJECT}_default', '--env-file', str(ENV_FILE),
              '--mount', f'type=volume,source={PROJECT}_models,target=/app/.local/models']
    docker('run', '--rm', *common, 'qinggui-assessment-api:latest', 'alembic', 'upgrade', 'head')
    receipt = json.loads(checked('exec', '-T', 'api', 'python', '-m', 'scripts.isolated_real_eval',
                                 'seed', '--database', DATABASE))
    docker('run', '-d', '--name', CONTAINER, '--restart', 'on-failure:3', '-p', '127.0.0.1:18085:8000',
           *common, 'qinggui-assessment-api:latest')
    print(json.dumps(receipt))


def run(label, only, cases=None):
    private = dotenv_values(ENV_FILE, interpolate=False)
    arguments = [os.sys.executable, '-m', 'evaluations.run', '--api-url', 'http://127.0.0.1:18085',
                 '--mode', 'live', '--label', label]
    if only:
        arguments += ['--only', only]
    if cases:
        arguments += ['--cases', cases]
    return subprocess.call(arguments, cwd=ROOT, env={**os.environ, 'DEMO_PASSWORD': private['DEMO_PASSWORD']})


def settle():
    docker('stop', CONTAINER)
    receipt = json.loads(checked('exec', '-T', 'api', 'python', '-m', 'scripts.isolated_real_eval',
                                 'settle', '--database', DATABASE))
    (ROOT / 'docs/evidence' / f'{DATABASE}-settlement.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['setup', 'run', 'settle'])
    parser.add_argument('--label', default='live-v19-full-01')
    parser.add_argument('--only', default='')
    parser.add_argument('--cases')
    parser.add_argument('--evaluation-id', default='v19', help='Unique evaluation ledger/container identifier')
    parser.add_argument('--resume-empty', action='store_true', help='Resume only an empty, interrupted setup database')
    args = parser.parse_args()
    if not re.fullmatch(r'v[0-9]+(?:_[a-z0-9]+)*', args.evaluation_id) or len(args.evaluation_id) > 35:
        parser.error('Invalid evaluation identifier')
    DATABASE = 'assessment_eval_' + args.evaluation_id
    CONTAINER = 'qinggui-assessment-eval-' + args.evaluation_id.replace('_','-')
    ENV_FILE = ROOT / '.local' / (args.evaluation_id + '-evaluation.env')
    if args.operation == 'setup':
        setup(args.resume_empty)
    elif args.operation == 'run':
        raise SystemExit(run(args.label, args.only, args.cases))
    else:
        settle()
