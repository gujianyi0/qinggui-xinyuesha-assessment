"""Exercise the real local web UI; requires optional playwright and installed Edge."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/evidence/browser")
    parser.add_argument("--complete-import", action="store_true", help="Wait for a real Worker to publish an index")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("browser evidence must stay inside this project")
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.screenshot(path=str(output / "login.png"), full_page=True)
        page.get_by_label("登录密码").fill("local-demo-change-me")
        page.get_by_role("button", name="进入工作区").click()
        expect(page.get_by_role("heading", name="问答工作台", exact=True)).to_be_visible()
        checks.append("login")
        page.get_by_label("输入问题").fill("诸葛亮有哪些技能？")
        page.get_by_role("button", name="发送问题").click()
        # The native integration profile loads the pinned CPU model on its first query.
        expect(page.locator(".message-assistant .message-text").last).to_contain_text("诸葛亮", timeout=120000)
        expect(page.get_by_role("button", name="发送问题")).to_be_visible()
        page.screenshot(path=str(output / "chat.png"), full_page=True)
        checks.append("chat_stream_and_citations")
        page.get_by_role("button", name="我的反馈", exact=True).click()
        page.get_by_label("实际现象", exact=False).fill("自动化演示：技能结算不符合预期")
        page.get_by_label("预期结果", exact=False).fill("符合规则说明")
        page.get_by_role("button", name="保存草稿", exact=True).click()
        expect(page.get_by_role("status")).to_contain_text("草稿已保存")
        page.get_by_label("预期结果", exact=False).fill("补充：应按规则依次结算")
        page.get_by_role("button", name="保存修改", exact=True).click()
        expect(page.locator(".editor-heading p")).to_contain_text("修订 v2")
        page.get_by_role("button", name="核对并确认", exact=True).click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.screenshot(path=str(output / "feedback-confirm.png"), full_page=True)
        page.get_by_role("button", name="确认保存反馈", exact=True).click()
        expect(page.get_by_role("status")).to_contain_text("反馈已保存")
        checks.append("draft_edit_revision_confirm")
        page.get_by_role("button", name="后台任务", exact=True).click()
        page.get_by_role("button", name="开始导入", exact=False).click()
        # A real Worker may claim the task before the first browser assertion.
        expect(page.locator(".job-card").first).to_be_visible()
        page.locator(".job-card").first.get_by_role("button", name="取消任务").click()
        expect(page.locator(".job-card").first).to_contain_text("已取消", timeout=20000)
        checks.append("job_submit_and_cancel")
        imported_job = None
        if args.complete_import:
            with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/jobs")) as submitted:
                page.get_by_role("button", name="开始导入", exact=False).click()
            imported_job = submitted.value.json()
            job_card = page.locator(".job-card").filter(has_text=imported_job["id"])
            expect(job_card).to_contain_text("已完成", timeout=180000)
            expect(job_card.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "100")
            page.screenshot(path=str(output / "native-import-completed.png"), full_page=True)
            checks.append("real_worker_import_and_publish")
        page.get_by_role("button", name="游戏资料库", exact=True).click()
        expect(page.locator(".entity-card").first).to_be_visible()
        page.screenshot(path=str(output / "library.png"), full_page=True)
        checks.append("catalog")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("button", name="打开导航")).to_be_visible()
        page.screenshot(path=str(output / "mobile.png"), full_page=False, animations="disabled")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "mobile horizontal overflow"
        checks.append("mobile_no_horizontal_overflow")
        health = page.request.get(args.url.rstrip('/') + '/api/health').json()
        browser.close()
    record = {"executed_at": datetime.now(timezone.utc).isoformat(), "url": args.url,
              "checks": checks, "page_errors": errors, "passed": not errors,
              "backend":health,
              "imported_job_id": imported_job["id"] if imported_job else None,
              "scope": "Edge browser using the recorded backend health; model mocks are not live model evidence"}
    (output / "summary.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    assert not errors


if __name__ == "__main__":
    main()
