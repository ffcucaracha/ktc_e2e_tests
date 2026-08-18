from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Iterator

import pytest
import urllib3
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower() or "step"


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("E2E_BASE_URL", "http://localhost:5173").rstrip("/")


@pytest.fixture(scope="session")
def screenshot_dir() -> Path:
    path = Path(os.getenv("E2E_SCREENSHOT_DIR", "artifacts/screenshots"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session", autouse=True)
def wait_for_app(base_url: str) -> None:
    http = urllib3.PoolManager()
    deadline = time.monotonic() + 90
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = http.request("GET", base_url, timeout=urllib3.Timeout(connect=2, read=2))
            if response.status < 500:
                return
            last_error = f"HTTP {response.status}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"frontend is not ready at {base_url}: {last_error}")


@pytest.fixture
def driver() -> Iterator[WebDriver]:
    options = Options()
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")

    remote_url = os.getenv("SELENIUM_REMOTE_URL")
    if remote_url:
        browser = webdriver.Remote(command_executor=remote_url, options=options)
    else:
        browser = webdriver.Chrome(options=options)

    browser.implicitly_wait(0.2)
    try:
        yield browser
    finally:
        browser.quit()


@pytest.fixture
def screenshot(driver: WebDriver, screenshot_dir: Path, request: pytest.FixtureRequest):
    counter = 0

    def save(name: str) -> Path:
        nonlocal counter
        counter += 1
        path = screenshot_dir / f"{counter:02d}-{slugify(request.node.name)}-{slugify(name)}.png"
        driver.save_screenshot(str(path))
        return path

    return save


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    browser = item.funcargs.get("driver")
    path = item.funcargs.get("screenshot_dir")
    if isinstance(browser, WebDriver) and isinstance(path, Path):
        browser.save_screenshot(str(path / f"failure-{slugify(item.name)}.png"))
