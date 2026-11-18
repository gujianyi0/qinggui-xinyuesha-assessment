"""Real browser, public relay, owner model and isolation check (two paid turns)."""
import argparse
import json
import time

import httpx
from playwright.sync_api import expect, sync_playwright

from backend.app.config import ROOT

URL = "https://qinggui-assessment.c2115259095.workers.dev"
OUT = ROOT / "docs/evidence/v18-public-service"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Reuse the preceding browser identity and retry its failed follow-up only")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    errors, requests, runs = [], [], []
    with httpx.Client(trust_env=False, timeout=15) as owner:
        before = owner.get("http://127.0.0.1:18081/health").json()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        if args.resume:
            previous = json.loads((ROOT / ".local/public-entry/browser-check.json").read_text(encoding="utf-8"))
            context.add_init_script("localStorage.setItem('qinggui-visitor-secret', " + json.dumps(previous["client_secret"]) + ")")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def record(response):
            if "/api/" not in response.url:
                return
            path = response.url.split("/api/", 1)[1]
            requests.append({"path": path, "method": response.request.method, "status": response.status})
            if path.endswith("/runs") and response.request.method == "POST" and response.status == 202:
                runs.append(response.json()["run_id"])

        page.on("response", record)
        page.goto("http://127.0.0.1:15176/", wait_until="networkidle")
        assert page.get_by_label("登录密码").count() == 0
        page.get_by_role("button", name="进入工作区").click()
        expect(page.get_by_role("heading", name="问答工作台", exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_text("真实问答服务已连接", exact=True)).to_be_visible(timeout=30000)
        assert page.get_by_role("button", name="后台任务", exact=False).count() == 0
        assert page.get_by_role("link", name="API 文档").count() == 0
        identity = page.evaluate("({auth: JSON.parse(sessionStorage.getItem('qinggui-public-auth')), secret: localStorage.getItem('qinggui-visitor-secret')})")
        (ROOT / ".local/public-entry/browser-check.json").write_text(json.dumps({"client_secret": identity["secret"], "user_id": identity["auth"]["user"]["id"]}), encoding="utf-8")
        questions = ["曹操有哪些技能？请说明技能原文、资料快照和来源。", "只解释刚才提到的奸雄：什么时候可以拿到牌？请保持同一个资料版本。"]
        offset = 0
        if args.resume:
            page.locator(".session-list button").first.click()
            expect(page.locator(".message-assistant").first).to_be_visible(timeout=15000)
            offset = page.locator(".message-assistant").count()
            questions = questions[1:]
        answers = []
        for index, question in enumerate(questions):
            page.get_by_label("输入问题", exact=True).fill(question)
            page.get_by_role("button", name="发送问题", exact=True).click()
            expect(page.get_by_role("button", name="取消回答", exact=True)).to_be_visible(timeout=15000)
            expect(page.get_by_role("button", name="取消回答", exact=True)).not_to_be_visible(timeout=180000)
            answer = page.locator(".message-assistant").nth(index + offset)
            text = answer.locator(".message-text").inner_text()
            if "奸雄" not in text or answer.locator(".citation-item").count() == 0:
                (OUT / "browser-failure-latest.json").write_text(json.dumps({"requests": requests, "answer": text, "errors": page.locator('[role="alert"]').all_text_contents(), "page_errors": errors, "run_ids": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
                page.screenshot(path=str(OUT / "browser-failure-latest.png"), full_page=True)
            assert "奸雄" in text and answer.locator(".citation-item").count() > 0, text
            answers.append({"question": question, "text": text, "visible_citations": answer.locator(".citation-item").count()})
        # Reproduce the previous focus action on the served remote client too.
        page.locator(".message-assistant .message-text").last.click()
        page.locator(".composer").click(position={"x": 5, "y": 24})
        expect(page.get_by_label("输入问题", exact=True)).to_be_focused()
        page.screenshot(path=str(OUT / "download-client-real-answer.png"), full_page=True)
        auth = page.evaluate("JSON.parse(sessionStorage.getItem('qinggui-public-auth'))")
        token = auth["access_token"]
        secret = page.evaluate("localStorage.getItem('qinggui-visitor-secret')")
        # The private browser identity can be reused for recovery, never published.
        private = ROOT / ".local/public-entry/browser-check.json"
        private.write_text(json.dumps({"client_secret": secret, "user_id": auth["user"]["id"]}), encoding="utf-8")
        with httpx.Client(timeout=30) as client:
            headers = {"Authorization": "Bearer " + token}
            results = [client.get(URL + "/api/runs/" + identifier, headers=headers).json() for identifier in runs]
            sessions = client.get(URL + "/api/sessions", headers=headers).json()
            assert len(sessions) == 1 and len(results) == len(questions)
            for result in results:
                assert result["status"] == "completed" and result["model_mode"] == "live"
            # A new browser identity must not inherit the first visitor's data.
            import secrets
            other = client.post(URL + "/api/auth/guest", json={"client_secret": secrets.token_urlsafe(32)}).json()
            second = {"Authorization": "Bearer " + other["access_token"]}
            assert client.get(URL + "/api/sessions", headers=second).json() == []
            assert client.get(URL + "/api/runs/" + runs[0], headers=second).status_code == 404
            assert client.get(URL + "/api/sessions/" + sessions[0]["id"] + "/messages", headers=second).status_code == 404
            assert client.post(URL + "/api/runs/" + runs[0] + "/cancel", headers=second).status_code == 404
            for method, path in [("GET", "/jobs"), ("POST", "/jobs"), ("POST", "/auth/token"), ("GET", "/docs"), ("POST", "/internal/qq/events")]:
                assert client.request(method, URL + "/api" + path, headers=headers, json={}).status_code == 404
            assert client.get(URL + "/__status").status_code == 401
            assert client.get(URL + "/api/sessions", headers={"Origin": "https://invalid.example"}).status_code == 403
            history = client.get(URL + "/api/sessions/" + sessions[0]["id"] + "/messages", headers=headers).json()
            assert len(history) >= 4 and history[-1]["content"] == answers[-1]["text"]
            page.reload(wait_until="networkidle")
            expect(page.get_by_role("heading", name="问答工作台", exact=True)).to_be_visible(timeout=15000)
            # Actual hosted public page also uses passwordless guest UI.
            hosted = context.new_page()
            hosted.goto(URL, wait_until="networkidle")
            assert hosted.get_by_label("登录密码").count() == 0
            hosted.screenshot(path=str(OUT / "hosted-login.png"), full_page=True)
            hosted.close()
        browser.close()
    for _ in range(15):
        with httpx.Client(trust_env=False, timeout=15) as client:
            after = client.get("http://127.0.0.1:18081/health").json()
        if after["budget"]["reserved_cny"] == 0:
            break
        time.sleep(1)
    assert not errors, errors
    summary = {"public_url": URL, "client_url": "http://127.0.0.1:15176/", "paid_turns": len(questions), "resumed_followup": args.resume,
               "answers": answers, "runs": results, "requests": requests, "page_errors": errors,
               "isolation": "passed", "management_routes": "blocked", "reload_persistence": "passed",
               "budget_before": before["budget"], "budget_after": after["budget"],
               "cost_delta_estimated_cny": after["budget"]["spent_cny"] - before["budget"]["spent_cny"]}
    (OUT / ("real-browser-retry.json" if args.resume else "real-browser-check.json")).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("public_url", "paid_turns", "page_errors", "isolation", "cost_delta_estimated_cny")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
