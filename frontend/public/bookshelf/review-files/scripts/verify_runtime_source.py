"""Compare deployed Python/data bytes without reading credentials or private rows."""
import argparse
import hashlib
import json
import re

from backend.app.config import ROOT
from scripts.docker_live import run_compose
from scripts.prepare_isolated_eval import docker


def verify(container, label):
    if not re.fullmatch(r'qinggui-assessment-eval-[a-z0-9-]+', container) or not re.fullmatch(r'v19-[a-z0-9-]+', label):
        raise ValueError('Use a named isolated evaluation container and v19 evidence label')
    names = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'backend').rglob('*.py')) + [
        'data/knowledge-boundaries.md','migrations/versions/0002_request_recovery.py','pyproject.toml','uv.lock','evaluations/run.py']
    code = f"""import hashlib,json,importlib.metadata
from pathlib import Path
names={names!r}
print(json.dumps(dict(version=importlib.metadata.version('qinggui-xinyuesha-assessment'),
 sha256={{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in names}})))
"""
    result = run_compose('exec','-T','api','python','-c',code)
    if result.returncode:
        raise RuntimeError('Primary source check failed')
    primary = json.loads(result.stdout)
    isolated = json.loads(docker('exec',container,'python','-c',code))
    expected = {n:hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in names}
    assert primary['version'] == '1.9.0' and primary == isolated and primary['sha256'] == expected
    (ROOT / 'docs/evidence' / f'{label}.json').write_text(json.dumps({
        'primary_and_evaluation_match':True, **primary},indent=2),encoding='utf-8')
    print(json.dumps({'matched':True,'source_files':len(names),'version':primary['version']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--label', required=True)
    args=parser.parse_args()
    verify(args.container,args.label)
