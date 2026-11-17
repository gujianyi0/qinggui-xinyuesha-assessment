"""Check the served frontend's focus/selection behavior using isolated API fixtures.

No model requests or database writes: every /api request is intercepted.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:15174")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/evidence/v17-input-focus/browser")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("evidence must stay in the assessment workspace")
    output.mkdir(parents=True, exist_ok=False)
    checks, errors = [], []
    runs = 0

    def fixture(route):
        nonlocal runs
        path = route.request.url.split("/api", 1)[1].split("?", 1)[0]
        if path == "/health":
            value = {"status": "ok", "model_mode": "mock", "snapshot_id": "fixture", "budget": {"spent_cny": 0, "reserved_cny": 0, "limit_cny": 200}}
        elif path == "/auth/token":
            value = {"access_token": "local-focus-fixture", "token_type": "bearer", "user": {"id": "fixture", "username": "alice"}}
        elif path == "/catalog/snapshots":
            value = [{"id": "fixture", "label": "焦点回归样例", "active": True}]
        elif path == "/sessions" and route.request.method == "POST":
            value = {"id": "focus-session", "title": "焦点回归", "created_at": "2026-11-12T00:00:00Z"}
        elif path.endswith("/runs"):
            runs += 1
            text = "这是用于点击和选择的模拟回答，不调用模型。\n可以选中复制这段回答。"
            events = [("started", {"run_id": "focus-run"}), ("delta", {"text": text}), ("completed", {"run_id": "focus-run", "text": text, "citations": []})]
            body = "".join(f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events)
            route.fulfill(status=200, content_type="text/event-stream", body=body)
            return
        else:
            value = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(value, ensure_ascii=False))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1.5)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/**", fixture)
        page.goto(args.url)
        password = page.get_by_label("登录密码")
        page.locator(".login-form").dispatch_event("mousedown", {"button": 0})
        expect(password).to_be_focused()
        password.fill("fixture-only")
        page.get_by_role("button", name="进入工作区").click()
        expect(page.get_by_role("heading", name="问答工作台", exact=True)).to_be_visible()
        checks.append("login_background_focus_and_submit")

        question = page.get_by_label("输入问题", exact=True)
        question.fill("展示焦点回归样例")
        page.get_by_role("button", name="发送问题").click()
        answer = page.locator(".message-assistant .message-text")
        expect(answer).to_contain_text("模拟回答")
        composer = page.locator(".composer")
        for index in range(6):
            answer.click()
            composer.click(position={"x": 3, "y": 30 if index % 2 else 45})
            expect(question).to_be_focused()
        metrics = question.evaluate("e => ({height:e.getBoundingClientRect().height,lineHeight:getComputedStyle(e).lineHeight,display:getComputedStyle(e).display,active:document.activeElement===e})")
        assert metrics["display"] == "block" and float(metrics["lineHeight"].removesuffix("px")) < metrics["height"]
        question.press("ArrowLeft")
        composer.screenshot(path=str(output / "composer-after.png"), caret="initial")
        checks.append("six_answer_then_blank_clicks_keep_native_textarea_focus")
        answer.dblclick()
        assert page.evaluate("window.getSelection().toString().length") > 0
        checks.append("answer_text_selection_remains_available")

        question.fill("中文输入测试")
        before = runs
        question.press("Shift+Enter")
        assert runs == before and "\n" in question.input_value()
        with page.expect_response("**/sessions/*/runs"):
            question.press("Enter")
        expect(question).to_be_empty()
        assert runs == before + 1
        checks.append("shift_enter_newline_and_enter_submit")

        page.get_by_role("button", name="我的反馈", exact=True).click()
        page.get_by_role("button", name="新建反馈", exact=True).click()
        for label in ("实际现象", "预期结果", "复现步骤", "局面与补充条件", "平台", "客户端版本"):
            field = page.get_by_label(label, exact=False)
            field.locator("xpath=..").dispatch_event("mousedown", {"button": 0})
            expect(field).to_be_focused()
        page.screenshot(path=str(output / "feedback-focus.png"))
        checks.append("six_feedback_fields_focus_their_own_control")
        page.get_by_role("button", name="游戏资料库", exact=True).click()
        page.locator(".search-field svg").click()
        expect(page.get_by_label("搜索资料")).to_be_focused()
        checks.append("search_surface_focus")

        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks.append("mobile_has_no_horizontal_overflow")
        assets = page.locator('script[src],link[rel="stylesheet"]').evaluate_all("nodes=>nodes.map(e=>e.src||e.href)")
        browser.close()
    result = {"executed_at": datetime.now(timezone.utc).isoformat(), "url": args.url,
              "scope": "served production frontend, API fixtures, no model requests/database writes; separate from live-model evaluations",
              "checks": checks, "page_errors": errors, "passed": not errors, "textarea": metrics,
              "web_assets": assets}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not errors
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
