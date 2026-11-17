"""Real public browser: lose one receipt, reload, and recover the original paid run."""
import argparse
import json
import re
import time

from playwright.sync_api import expect, sync_playwright

from backend.app.config import ROOT


def main(label):
    if not label.startswith('v19-browser-') or '/' in label or '\\' in label or '..' in label:
        raise ValueError('Use a unique v19-browser- label')
    output = ROOT / 'docs/evidence' / label
    output.mkdir(parents=True, exist_ok=False)
    report = {'passed':False, 'scope':'Actual public UI and owner live API; one intentional paid question',
              'started_at':time.time(), 'submission_posts':0, 'request_lookups':0, 'network':[]}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        receipt = {}
        errors = []
        page.on('pageerror', lambda error: errors.append(type(error).__name__))
        page.on('response', lambda response: report['network'].append({
            'path':response.url.split('/api/',1)[-1].split('?',1)[0], 'status':response.status,
            'elapsed':round(time.time()-report['started_at'],3)
        }) if '/api/' in response.url else None)

        def lose_receipt(route):
            report['submission_posts'] += 1
            response = route.fetch(timeout=60000)
            assert response.status == 202, response.status
            receipt.update(response.json())
            report['run_id'] = receipt['run_id']
            # The server has committed. Simulate losing only the acknowledgement.
            route.abort('failed')

        def count_lookup(request):
            if '/requests/' in request.url and request.method == 'GET':
                report['request_lookups'] += 1

        page.route('**/sessions/*/submissions', lose_receipt)
        page.on('request', count_lookup)
        try:
            page.goto('https://qinggui-assessment.c2115259095.workers.dev/', wait_until='domcontentloaded', timeout=60000)
            page.get_by_role('button', name='进入工作区').click()
            expect(page.get_by_role('heading', name='问答工作台', exact=True)).to_be_visible(timeout=60000)
            page.get_by_label('输入问题').fill('查询标准诸葛亮的势力、体力与技能。')
            page.get_by_role('button', name='发送问题').click()
            deadline = time.monotonic() + 120
            retried_setup = False
            while not receipt:
                if time.monotonic() > deadline:
                    raise TimeoutError('Submission receipt not observed')
                # A failed session creation has not submitted a paid run. Retry
                # this setup only; never retry once any submission was observed.
                if not retried_setup and report['submission_posts'] == 0 and page.get_by_role('alert').count() and page.get_by_role('button', name='发送问题').is_enabled():
                    retried_setup = True
                    page.get_by_role('button', name='发送问题').click()
                page.wait_for_timeout(100)
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_role('button', name='恢复原请求')).to_be_visible(timeout=60000)
            expect(page.get_by_role('button', name='恢复原请求')).to_be_enabled(timeout=60000)
            page.get_by_role('button', name='恢复原请求').click()
            expect(page.locator('.message-assistant .message-text').last).to_contain_text('空城', timeout=150000)
            expect(page.get_by_role('button', name='发送问题')).to_be_visible(timeout=30000)
            assert report['submission_posts'] == 1 and report['request_lookups'] >= 1
            expect(page.get_by_role('button', name='恢复原请求')).to_have_count(0)
            page.screenshot(path=str(output / 'recovered.png'), full_page=True)
            body = page.locator('.message-assistant .message-text').last.inner_text()
            page.reload(wait_until='domcontentloaded')
            # Completed requests no longer carry a pending marker. The app's
            # normal landing is a new chat; open the saved conversation explicitly.
            page.get_by_role('button', name=re.compile('查询标准诸葛亮')).click(timeout=60000)
            expect(page.locator('.message-assistant .message-text').last).to_have_text(body, timeout=60000)
            report.update(passed=True, run_id=receipt['run_id'], duplicate_paid_submission=False,
                          answer_persisted_after_reload=True, page_errors=errors)
            assert not errors
        finally:
            if not report['passed']:
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
            report['elapsed_seconds'] = round(time.time()-report.pop('started_at'),3)
            (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            browser.close()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='v19-browser-recovery-02')
    main(parser.parse_args().label)
