"""Verify shelf documents, file previews, source bytes and private boundaries."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

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
    assert len(data['groups']) == 7 and len(data['records']) == 49
    assert all(r['kind'] == 'learning' for r in data['records'])
    review = data['reviewDocuments']
    assert len(review) == 12
    assert review[-1]['sourcePath'] == 'README.md'
    assert all(r['kind'] == 'assessment_reference' and 'group' not in r for r in review)
    assert not set(r['id'] for r in review) & set(r['id'] for r in data['records'])
    for path, metadata in data['evidenceFiles'].items():
        assert path in data['evidenceLinks']
        assert metadata['url'].startswith('/bookshelf/review-files/')
        exported = SHELF / unquote(metadata['url']).removeprefix('/bookshelf/')
        assert exported.resolve().is_relative_to(SHELF.resolve())
        assert hashlib.sha256(exported.read_bytes()).hexdigest() == metadata['sha256'], path
    for record in data['records']:
        original = ROOT / 'tools/bookshelf/base/originals' / (record['id'] + '.md')
        exported = SHELF / 'originals' / (record['id'] + '.md')
        assert original.read_bytes() == exported.read_bytes()
        assert hashlib.sha256(exported.read_bytes()).hexdigest() == record['hash'], original
    for record in review:
        source = ROOT / 'docs/文档导航QA' / record['filename']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['hash'], source
    for record in manifest['files']:
        source = ROOT / record['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256'], source
    private = dotenv_values(ROOT / '.env.docker-live', interpolate=False)
    secrets = [private.get(key) for key in ['MODEL_API_KEY', 'POSTGRES_PASSWORD', 'PUBLIC_SERVICE_TOKEN', 'BOOKSHELF_OWNER_KEY']]
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
            elif url == '/' and 'page=bookshelf' in value.query:
                query = parse_qs(value.query)
                if 'document' in query:
                    assert query['document'][0] in {r['id'] for r in data['records'] + review}, (file, href)
                if 'file' in query:
                    target_path = query['file'][0]
                    assert (target_path == '.' or target_path in data['evidenceLinks']
                            or any(p.startswith(target_path.rstrip('/') + '/') for p in data['evidenceFiles'])), (file, href)
                count += 1
                continue
            elif url.startswith('/'):
                raise AssertionError(f'Unexpected root link in {file}: {href}')
            else:
                # Index uses /bookshelf/ as its base; article fragments render there.
                target = (SHELF if file.parent.name == 'articles' else file.parent) / url
            assert target.resolve().is_relative_to(SHELF.resolve()), (file, href)
            assert target.exists(), (file, href)
            count += 1
    assert not (SHELF / 'app.js').exists()
    assert not (SHELF / 'shared-progress.js').exists()
    result = {'review_documents': len(review), 'learning_goals': 49, 'linked_source_files': len(manifest['files']),
              'local_links_checked': count, 'private_values_found': 0, 'owner_credentials_in_static_assets': False,
              'historical_missing_paths': manifest['unexported']}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    verify()
