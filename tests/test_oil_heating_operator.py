from __future__ import annotations

import os
import time
from collections.abc import Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver, WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


Wait = WebDriverWait
Screenshot = Callable[[str], object]


def wait(driver: WebDriver, seconds: int = 20) -> Wait:
    return WebDriverWait(driver, seconds)


def css(driver: WebDriver, selector: str, seconds: int = 20) -> WebElement:
    return wait(driver, seconds).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))


def clickable_css(driver: WebDriver, selector: str, seconds: int = 20) -> WebElement:
    return wait(driver, seconds).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))


def click_text(driver: WebDriver, text: str, seconds: int = 20) -> None:
    xpath = f"//*[self::button or self::a][normalize-space(.)='{text}']"
    wait(driver, seconds).until(EC.element_to_be_clickable((By.XPATH, xpath))).click()


def login_as_operator(driver: WebDriver, base_url: str, screenshot: Screenshot) -> None:
    driver.get(f"{base_url}/login")
    css(driver, "input[name='username']").send_keys(os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"))
    css(driver, "input[name='password']").send_keys(
        os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
    )
    clickable_css(driver, "button[type='submit']").click()
    wait(driver).until(EC.url_contains("/operator/simulators"))
    screenshot("01-operator-catalog")


def open_oil_heating_simulator(driver: WebDriver, screenshot: Screenshot) -> None:
    card_link = wait(driver).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[contains(normalize-space(.), 'oil-heating-v1')]"
                "/ancestor::*[contains(@class, 'MuiCard-root')][1]//a",
            ),
        ),
    )
    card_link.click()
    wait(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".MuiChip-root")))
    screenshot("02-oil-heating-detail")


def start_session(driver: WebDriver, screenshot: Screenshot) -> None:
    clickable_css(driver, "button.MuiButton-contained").click()
    wait(driver, 30).until(EC.url_contains("/operator/sessions/"))
    css(driver, "svg[aria-labelledby='oil-heating-title oil-heating-desc']", 30)
    screenshot("03-session-started")


def click_pump(driver: WebDriver, pump_id: str) -> None:
    button = wait(driver).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, f"button[aria-label$=' {pump_id}']")),
    )
    button.click()


def slider_input(driver: WebDriver, regulator_id: str) -> WebElement:
    return css(driver, f"[aria-label='{regulator_id} valve']")


def set_slider(driver: WebDriver, regulator_id: str, target_value: int) -> int:
    slider = slider_input(driver, regulator_id)
    slider.send_keys(Keys.HOME)
    for _ in range(target_value):
        slider.send_keys(Keys.ARROW_RIGHT)
    return read_slider_value(driver, regulator_id)


def read_slider_value(driver: WebDriver, regulator_id: str) -> int:
    return int(float(slider_input(driver, regulator_id).get_attribute("value") or "0"))


def apply_regulator(driver: WebDriver, regulator_id: str) -> None:
    selector = f"[data-testid='regulator-{regulator_id}'] button"
    wait(driver).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()


def changed_target(current_value: int, delta: int) -> int:
    target = (current_value + delta) % 101
    if target == current_value:
        return (current_value + 1) % 101
    return target


def test_operator_can_run_oil_heating_and_adjust_valves(
    driver: WebDriver,
    base_url: str,
    screenshot: Screenshot,
) -> None:
    login_as_operator(driver, base_url, screenshot)
    open_oil_heating_simulator(driver, screenshot)
    start_session(driver, screenshot)

    for pump_id in ("H1A", "H1B", "H1V"):
        click_pump(driver, pump_id)
    screenshot("04-pumps-started")

    targets = {
        "FRC404": changed_target(read_slider_value(driver, "FRC404"), 35),
        "FRC405": changed_target(read_slider_value(driver, "FRC405"), 55),
        "FRC406": changed_target(read_slider_value(driver, "FRC406"), 75),
    }
    for regulator_id, target in targets.items():
        observed = set_slider(driver, regulator_id, target)
        assert observed == target, f"{regulator_id} did not move to requested value"
    screenshot("05-valves-moved-before-polling")

    time.sleep(3)
    screenshot("06-valves-after-polling")
    for regulator_id, target in targets.items():
        observed = read_slider_value(driver, regulator_id)
        assert observed == target, f"{regulator_id} reset from {target} to {observed} before apply"

    for regulator_id in targets:
        apply_regulator(driver, regulator_id)
    screenshot("07-valves-applied")

    time.sleep(3)
    screenshot("08-valves-after-apply-refresh")
    for regulator_id, target in targets.items():
        observed = read_slider_value(driver, regulator_id)
        assert observed == target, f"{regulator_id} reset from {target} to {observed} after apply"

    assert "operator/sessions" in driver.current_url
