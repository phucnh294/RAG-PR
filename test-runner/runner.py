"""Playwright execution for the test-runner service.

This module never executes code it receives: test cases arrive as a small step DSL
(goto/fill/click/expect_*) and each step is mapped onto one Playwright call here.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from urllib.parse import urljoin

from PIL import Image
from playwright.async_api import Browser, Page, async_playwright, expect
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator as PwLocator

from models import (
    CaptureRequest,
    CaptureResponse,
    CaseResult,
    DomElement,
    Locator,
    RunRequest,
    StepResult,
    TestCaseSpec,
    TestStep,
)

logger = logging.getLogger("test_runner")

_MAX_ERROR_CHARS = 600

# Collects every element an agent could interact with or assert on, INCLUDING hidden
# ones (validation messages, the success banner) — they are part of the page's contract
# even before they show up.
_EXTRACT_ELEMENTS_JS = """
() => {
  const implicitRole = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'form') return 'form';
    if (tag === 'input') {
      if (['button', 'submit', 'reset'].includes(type)) return 'button';
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      return 'textbox';
    }
    return null;
  };
  const labelOf = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    return el.getAttribute('aria-label');
  };
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim() || null;
  const selector = 'input, select, textarea, button, a[href], h1, h2, h3, h4, h5, h6, form, [role]';
  return Array.from(document.querySelectorAll(selector)).map((el) => {
    const tag = el.tagName.toLowerCase();
    const label = clean(labelOf(el));
    const text = ['input', 'select', 'textarea', 'form'].includes(tag) ? null : clean(el.innerText || el.textContent);
    const style = window.getComputedStyle(el);
    return {
      tag,
      type: el.getAttribute('type'),
      id: el.id || null,
      name: el.getAttribute('name'),
      label,
      required: el.hasAttribute('required'),
      placeholder: el.getAttribute('placeholder'),
      role: el.getAttribute('role') || implicitRole(el),
      accessible_name: label || text,
      text,
      test_id: el.getAttribute('data-testid'),
      visible: !el.hidden && style.display !== 'none' && style.visibility !== 'hidden',
    };
  });
}
"""


def _trim(message: str) -> str:
    message = message.strip()
    return message if len(message) <= _MAX_ERROR_CHARS else message[:_MAX_ERROR_CHARS] + "…"


def _resolve(page: Page, locator: Locator) -> PwLocator:
    if locator.strategy == "role":
        return page.get_by_role(
            locator.value,  # type: ignore[arg-type]  # validated by Playwright at runtime
            name=locator.name,
            exact=locator.exact,
        )
    if locator.strategy == "label":
        return page.get_by_label(locator.value, exact=locator.exact)
    if locator.strategy == "testid":
        return page.get_by_test_id(locator.value)
    if locator.strategy == "text":
        return page.get_by_text(locator.value, exact=locator.exact)
    return page.locator(locator.value)


def _require_locator(step: TestStep) -> Locator:
    if step.locator is None:
        raise ValueError(f"step '{step.action}' needs a locator")
    return step.locator


async def _execute_step(page: Page, step: TestStep, base_url: str, timeout_ms: int) -> None:
    action = step.action
    if action == "goto":
        await page.goto(urljoin(base_url, step.value or ""), timeout=timeout_ms)
        return
    if action == "expect_url":
        await expect(page).to_have_url(re.compile(re.escape(step.value or "")), timeout=timeout_ms)
        return

    target = _resolve(page, _require_locator(step))
    if action == "fill":
        await target.fill(step.value or "", timeout=timeout_ms)
    elif action == "click":
        await target.click(timeout=timeout_ms)
    elif action == "expect_visible":
        await expect(target).to_be_visible(timeout=timeout_ms)
    elif action == "expect_hidden":
        await expect(target).to_be_hidden(timeout=timeout_ms)
    elif action == "expect_text":
        await expect(target).to_contain_text(step.value or "", timeout=timeout_ms)
    elif action == "expect_value":
        await expect(target).to_have_value(step.value or "", timeout=timeout_ms)
    else:  # pragma: no cover - StepAction is a closed Literal
        raise ValueError(f"unknown action {action!r}")


_OBSERVE_TIMEOUT_MS = 1000
_MAX_OBSERVED_CHARS = 300


async def _observe(page: Page, step: TestStep) -> str | None:
    """Record what the page actually shows for a step, so the evidence says WHY it passed
    or failed (e.g. expected "Email is required." but the element said "")."""
    try:
        if step.action in ("goto", "expect_url"):
            return f"url={page.url}"
        if step.locator is None:
            return None
        target = _resolve(page, step.locator)
        count = await target.count()
        if count == 0:
            return "matched 0 elements"
        first = target.first
        prefix = f"matched {count} element(s); " if count > 1 else ""
        if step.action in ("fill", "expect_value"):
            value = await first.input_value(timeout=_OBSERVE_TIMEOUT_MS)
            return f"{prefix}value={value!r}"[:_MAX_OBSERVED_CHARS]
        if step.action == "expect_text":
            text = await first.inner_text(timeout=_OBSERVE_TIMEOUT_MS)
            return f"{prefix}text={text.strip()!r}"[:_MAX_OBSERVED_CHARS]
        if step.action in ("expect_visible", "expect_hidden", "click"):
            return f"{prefix}visible={await first.is_visible()}"
    except (PlaywrightError, ValueError) as error:
        return f"could not observe: {_trim(str(error))[:200]}"
    return None


# Visible alerts/status banners, labelled by id or data-testid when they have one.
_PAGE_MESSAGES_JS = """
() => Array.from(document.querySelectorAll('[role=alert], [role=status], [aria-live]'))
  .filter((el) => {
    const style = window.getComputedStyle(el);
    return !el.hidden && style.display !== 'none' && style.visibility !== 'hidden';
  })
  .map((el) => {
    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    const name = el.id || el.getAttribute('data-testid');
    return text ? (name ? `${name}: ${text}` : text) : null;
  })
  .filter((message, index, all) => message && all.indexOf(message) === index)
"""


async def _page_messages(page: Page) -> list[str]:
    try:
        messages = await page.evaluate(_PAGE_MESSAGES_JS)
    except PlaywrightError:
        return []
    return [str(message)[:_MAX_OBSERVED_CHARS] for message in messages]


async def _evidence(
    page: Page, step: TestStep
) -> tuple[str | None, list[str], str | None]:
    """(observed, visible page messages, screenshot base64) captured right after a step;
    never raises."""
    observed = await _observe(page, step)
    messages = await _page_messages(page)
    try:
        screenshot = base64.b64encode(await page.screenshot(full_page=True)).decode()
    except PlaywrightError:
        screenshot = None
    return observed, messages, screenshot


async def _run_case(
    browser: Browser,
    case: TestCaseSpec,
    base_url: str,
    timeout_ms: int,
    capture_evidence: bool = True,
) -> CaseResult:
    """Run one case in a fresh browser context (no shared cookies/localStorage), stopping
    at the first failing step; the remaining steps are reported as skipped. With
    capture_evidence, every executed step gets a screenshot and an observed value."""
    started = time.monotonic()
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()
    console_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    page.on("pageerror", lambda error: console_errors.append(str(error)))

    results: list[StepResult] = []
    status = "passed"
    screenshot: str | None = None
    try:
        for index, step in enumerate(case.steps):
            if status != "passed":
                results.append(_step_result(index, step, "skipped"))
                continue
            step_started = time.monotonic()
            try:
                await _execute_step(page, step, base_url, timeout_ms)
                result = _step_result(index, step, "passed", started_at=step_started)
            except (PlaywrightError, AssertionError, ValueError) as error:
                status = "failed"
                result = _step_result(
                    index, step, "failed", error=_trim(str(error)), started_at=step_started
                )
            if capture_evidence:
                (
                    result.observed,
                    result.page_messages,
                    result.screenshot_png_b64,
                ) = await _evidence(page, step)
            elif status == "failed":
                screenshot = base64.b64encode(await page.screenshot(full_page=True)).decode()
            results.append(result)
    except PlaywrightError as error:
        # The browser/page itself died (not a step assertion): report the case as error.
        status = "error"
        results.append(
            StepResult(index=len(results), action="goto", status="failed", error=_trim(str(error)))
        )
    finally:
        await context.close()

    return CaseResult(
        case_id=case.case_id,
        status=status,  # type: ignore[arg-type]
        duration_ms=round((time.monotonic() - started) * 1000, 1),
        steps=results,
        failure_screenshot_png_b64=screenshot,
        console_errors=console_errors,
    )


def _step_result(
    index: int,
    step: TestStep,
    status: str,
    error: str | None = None,
    started_at: float | None = None,
) -> StepResult:
    duration = round((time.monotonic() - started_at) * 1000, 1) if started_at else 0.0
    return StepResult(
        index=index,
        action=step.action,
        locator=step.locator,
        value=step.value,
        status=status,  # type: ignore[arg-type]
        error=error,
        duration_ms=duration,
    )


async def run_cases(request: RunRequest) -> list[CaseResult]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            results = []
            for case in request.cases:
                logger.info("Running case %s (%d steps)", case.case_id, len(case.steps))
                result = await _run_case(
                    browser,
                    case,
                    request.base_url,
                    request.default_timeout_ms,
                    capture_evidence=request.capture_evidence,
                )
                logger.info("Case %s -> %s", case.case_id, result.status)
                results.append(result)
            return results
        finally:
            await browser.close()


def _downscale_png(png: bytes, max_width: int) -> bytes:
    image = Image.open(io.BytesIO(png))
    if image.width <= max_width:
        return png
    height = round(image.height * max_width / image.width)
    output = io.BytesIO()
    image.resize((max_width, height), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue()


async def capture_page(request: CaptureRequest) -> CaptureResponse:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                viewport={"width": request.viewport_width, "height": request.viewport_height}
            )
            page = await context.new_page()
            await page.goto(request.url, wait_until="networkidle")
            screenshot = await page.screenshot(full_page=True)
            elements = await page.evaluate(_EXTRACT_ELEMENTS_JS)
            return CaptureResponse(
                final_url=page.url,
                title=await page.title(),
                screenshot_png_b64=base64.b64encode(screenshot).decode(),
                vision_png_b64=base64.b64encode(
                    _downscale_png(screenshot, request.vision_max_width)
                ).decode(),
                aria_snapshot=await page.locator("body").aria_snapshot(),
                elements=[DomElement.model_validate(element) for element in elements],
            )
        finally:
            await browser.close()
