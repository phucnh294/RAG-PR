"""test-runner: an internal HTTP service that drives a headless Chromium via Playwright.

The backend's Agents pipeline calls it to (1) capture a page — screenshot, accessibility
snapshot and interactive elements — for the UI-analysis agent, and (2) execute the
structured test cases the test-design agent produced. Keeping the browser here keeps
~1 GB of Chromium out of the backend image, and browsing happens in a process that holds
no database or API credentials.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from playwright.async_api import Error as PlaywrightError

from models import CaptureRequest, CaptureResponse, RunRequest, RunResponse
from runner import capture_page, run_cases

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("test_runner")

app = FastAPI(title="test-runner")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/capture", response_model=CaptureResponse)
async def capture(request: CaptureRequest) -> CaptureResponse:
    logger.info("Capture %s", request.url)
    try:
        return await capture_page(request)
    except PlaywrightError as error:
        logger.warning("Capture failed for %s: %s", request.url, error)
        raise HTTPException(status_code=502, detail=f"Could not load page: {error}") from error


@app.post("/run", response_model=RunResponse)
async def run(request: RunRequest) -> RunResponse:
    logger.info("Run %d case(s) against %s", len(request.cases), request.base_url)
    return RunResponse(cases=await run_cases(request))
