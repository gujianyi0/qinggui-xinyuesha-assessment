"""Boot a restored isolated DB with model billing disabled and read saved history."""
import argparse
import json
import re
import time

import httpx
from dotenv import dotenv_values
from sqlalchemy import URL

from backend.app.config import ROOT
from scripts.backup_docker_primary import label_path
from scripts.docker_live import PROJECT
from scripts.prepare_isolated_eval import docker


def verify(label, database):
    started = time.monotonic()
    if not re.fullmatch(r'assessment_restore_[a-z0-9_]{1,40}', database):
        raise ValueError('Only isolated restore databases are accepted')
    report = json.loads((ROOT / 'docs/evidence' / f'{label}-restore.json').read_text(encoding='utf-8'))
    if not report['passed'] or report['target'] != database:
        raise ValueError('A matching successful restore fingerprint is required')
    private = dotenv_values(label_path(label) / 'private-config/.env.docker-live', interpolate=False)
    private.update(DATABASE_URL=URL.create('postgresql+asyncpg', username='assessment', password=private['POSTGRES_PASSWORD'],
                                         host='postgres', port=5432, database=database).render_as_string(hide_password=False),
                   MODEL_MODE='mock', MODEL_API_KEY='', CREATE_SCHEMA='false', SEED_USERS='false',
                   ENABLE_TEST_FAULTS='false', REDIS_URL='redis://127.0.0.1:1/0')
    if any('\n' in str(value) or '\r' in str(value) for value in private.values() if value is not None):
        raise ValueError('Multiline environment values are unsupported')
    path = ROOT / '.local/backups' / label / 'restore-probe.env'
    path.write_text(''.join(f'{key}={value}\n' for key, value in private.items() if value is not None), encoding='utf-8')
    name = 'qinggui-v19-restored-probe'
    docker('run', '-d', '--name', name, '--network', PROJECT + '_default', '--env-file', str(path),
           '-p', '127.0.0.1:18086:8000', 'qinggui-assessment-api:latest')
    try:
        with httpx.Client(base_url='http://127.0.0.1:18086', trust_env=False, timeout=10) as client:
            deadline = time.monotonic() + 60
            while True:
                try:
                    response = client.get('/health')
                    response.raise_for_status()
                    health = response.json()
                    break
                except httpx.HTTPError:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Restored API did not become healthy') from None
                    time.sleep(.5)
            assert health['model_mode'] == 'mock' and health['budget']['spent_cny'] == report['budget']['spent']
            response = client.post('/auth/token', json={'username':'alice', 'password':private['DEMO_PASSWORD']})
            response.raise_for_status()
            client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
            sessions = client.get('/sessions').json()
            assert sessions
            readable = 0
            for session in sessions[:3]:
                response = client.get('/sessions/' + session['id'] + '/messages')
                response.raise_for_status()
                readable += len(response.json())
            final = client.get('/health').json()
            assert final['budget'] == health['budget']
        evidence = {'passed': True, 'backup':label, 'target':database, 'model_mode':'mock',
                    'provider_key_loaded':False, 'model_requests_sent':0, 'sessions_read':len(sessions),
                    'messages_read':readable, 'budget_preserved':True, 'primary_database_used':False}
        evidence['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (ROOT / 'docs/evidence' / f'{label}-api-restore.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps(evidence))
    finally:
        docker('stop', name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    verify(args.label, args.database)
