"""Verify the local read-only review shelf, source bytes, links and private boundary."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SHELF = ROOT / 'frontend/public/bookshelf'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {'href', 'src'} and value:
                self.links.append(value)


def verify():
    data = json.loads((SHELF / 'data.json').read_text(encoding='utf-8'))
    manifest = json.loads((SHELF / 'export-manifest.json').read_text(encoding='utf-8'))
    assert len(data['groups']) == 8 and data['groups'][7]['title'] == '文档导航QA'
    assert len([r for r in data['records'] if r['group'] < 7]) == 49
    review = [r for r in data['records'] if r['group'] == 7]
    assert len(review) == 11
    for record in review:
        source = ROOT / 'docs/文档导航QA' / record['filename']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['hash'], source
    for record in manifest['files']:
        source = ROOT / record['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256'], source
    private = dotenv_values(ROOT / '.env.docker-live', interpolate=False)
    secrets = [private.get(key) for key in ['MODEL_API_KEY', 'POSTGRES_PASSWORD', 'PUBLIC_SERVICE_TOKEN']]
    owner = ROOT.parent / '知识浏览网页/.local/owner-access.json'
    if owner.exists():
        credentials = json.loads(owner.read_text(encoding='utf-8'))
        secrets.extend(credentials.get(key) for key in ['key', 'sessionSecret'])
    count = 0
    for file in SHELF.rglob('*'):
        if not file.is_file():
            continue
        parts = file.relative_to(SHELF).parts
        assert not any(p in {'.local', '.git', 'node_modules', 'git'} or (p.startswith('.env') and p != '.env.example') for p in parts)
        raw = file.read_bytes()
        assert not any(secret and secret.encode() in raw for secret in secrets), file
        if file.suffix != '.html':
            continue
        parser = Links()
        parser.feed(raw.decode('utf-8'))
        for href in parser.links:
            value = urlsplit(href)
            if value.scheme or value.netloc or not value.path:
                continue
            url = unquote(value.path)
            if url.startswith('/bookshelf/'):
                target = SHELF / url.removeprefix('/bookshelf/')
            elif url.startswith('/'):
                raise AssertionError(f'Unexpected root link in {file}: {href}')
            else:
                # Index uses /bookshelf/ as its base; article fragments render there.
                target = (SHELF if file.parent.name == 'articles' else file.parent) / url
            assert target.resolve().is_relative_to(SHELF.resolve()), (file, href)
            assert target.exists(), (file, href)
            count += 1
    assert 'fetch(' not in (SHELF / 'shared-progress.js').read_text(encoding='utf-8')
    result = {'review_documents': 11, 'learning_goals': 49, 'linked_source_files': len(manifest['files']),
              'local_links_checked': count, 'private_values_found': 0, 'cloud_progress_connected': False,
              'historical_missing_paths': manifest['unexported']}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    verify()
