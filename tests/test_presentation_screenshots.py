from __future__ import annotations

import os
import time
from collections.abc import Callable

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver, WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


Screenshot = Callable[[str], object]


def wait(driver: WebDriver, seconds: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def login(
    driver: WebDriver,
    base_url: str,
    *,
    username: str,
    password: str,
    expected_path: str,
) -> None:
    driver.get(f"{base_url}/login")
    wait(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='username']"))).send_keys(username)
    driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(password)
    wait(driver).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()
    wait(driver).until(EC.url_contains(expected_path))


def text_element(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    return wait(driver, seconds).until(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(normalize-space(.), {text!r})]")),
    )


def scroll_to_text(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    element = text_element(driver, text, seconds)
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", element)
    time.sleep(0.5)
    return element


def save_after_scroll(driver: WebDriver, screenshot: Screenshot, text: str, name: str) -> None:
    scroll_to_text(driver, text)
    screenshot(name)


def open_elou_simulator(driver: WebDriver) -> None:
    cards = wait(driver).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".MuiCard-root")),
    )
    target = next((card for card in cards if "ЭЛОУ" in card.text.upper()), None)
    if target is None:
        target = next((card for card in cards if "ELOU" in card.text.upper()), None)
    if target is None:
        raise AssertionError("Карточка тренажёра ЭЛОУ не найдена")
    target.find_element(By.XPATH, ".//a[normalize-space(.)='Открыть']").click()
    text_element(driver, "Подготовка тренировки")


def try_intentional_wrong_action(driver: WebDriver) -> None:
    # В полном сценарии ожидаемым первым действием является KR1. H1B/H1C раньше KR1
    # дают наглядную ошибку последовательности, если кнопки присутствуют в текущей визуализации.
    for equipment_id in ("H1B", "H1C", "H1A"):
        buttons = driver.find_elements(By.CSS_SELECTOR, f"button[aria-label*='{equipment_id}']")
        clickable = next((button for button in buttons if button.is_displayed() and button.is_enabled()), None)
        if clickable is not None:
            clickable.click()
            return


def wait_for_ml_risk_warning(driver: WebDriver, screenshot: Screenshot) -> bool:
    """Wait until the loaded model crosses its configured threshold.

    The AI service exposes a non-null predicted_error_code only when the CatBoost
    probability is greater than or equal to the threshold stored in model metadata.
    Waiting for the prediction chip therefore follows the active model threshold
    instead of hard-coding 20% in the Selenium test.
    """
    timeout = max(1, int(os.getenv("E2E_PRESENTATION_AI_WAIT_SECONDS", "30")))
    locator = (
        By.XPATH,
        "//*[contains(normalize-space(.), 'Прогноз: ERROR_IN_NEXT_10_SECONDS')]",
    )
    try:
        wait(driver, timeout).until(EC.visibility_of_element_located(locator))
        return True
    except TimeoutException:
        print(
            f"ML risk warning did not appear within {timeout}s; "
            "saving a diagnostic screenshot and continuing presentation capture.",
            flush=True,
        )
        screenshot("presentation-05-live-ml-risk-diagnostic")
        return False


def stop_session_and_wait_for_result(driver: WebDriver) -> None:
    stop_button = wait(driver, 30).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(normalize-space(.), 'Завершить сессию')]"),
        ),
    )
    stop_button.click()

    try:
        wait(driver, 150).until(EC.url_contains("/result"))
        text_element(driver, "Итоговый разбор сессии", 150)
    except Exception:
        retry = driver.find_elements(By.XPATH, "//button[normalize-space(.)='Повторить']")
        if not retry:
            raise
        retry[0].click()
        text_element(driver, "Итоговый разбор сессии", 150)


@pytest.mark.presentation
def test_operator_presentation_screenshots(
    driver: WebDriver,
    base_url: str,
    screenshot: Screenshot,
) -> None:
    """Capture the operator screens used in the championship presentation."""
    driver.set_window_size(1600, 1000)
    login(
        driver,
        base_url,
        username=os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        password=os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
        expected_path="/operator/simulators",
    )

    text_element(driver, "Тренажёры")
    screenshot("presentation-01-operator-catalog")
    save_after_scroll(driver, screenshot, "История прохождений", "presentation-02-training-history")

    driver.execute_script("window.scrollTo(0, 0);")
    open_elou_simulator(driver)
    screenshot("presentation-03-elou-scenario-selection")

    wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Начать']")),
    ).click()
    wait(driver, 60).until(EC.url_contains("/operator/sessions/"))
    text_element(driver, "AI-инструктор", 60)
    screenshot("presentation-04-live-elou-and-ai-instructor")

    try_intentional_wrong_action(driver)
    if wait_for_ml_risk_warning(driver, screenshot):
        screenshot("presentation-05-live-ml-risk-warning")

    stop_session_and_wait_for_result(driver)
    screenshot("presentation-06-result-summary")
    save_after_scroll(driver, screenshot, "Timeline ключевых событий", "presentation-07-timeline-ml-and-errors")
    save_after_scroll(driver, screenshot, "Ошибки с объяснениями", "presentation-08-errors-with-explanations")
    save_after_scroll(driver, screenshot, "Интеллектуальный debrief", "presentation-09-llm-debrief")
    save_after_scroll(
        driver,
        screenshot,
        "Рекомендованная следующая тренировка",
        "presentation-10-adaptive-next-training",
    )


@pytest.mark.presentation
def test_admin_presentation_screenshots(
    driver: WebDriver,
    base_url: str,
    screenshot: Screenshot,
) -> None:
    """Capture the administrator and ML transparency screens for the presentation."""
    driver.set_window_size(1600, 1000)
    login(
        driver,
        base_url,
        username=os.getenv("E2E_ADMIN_USERNAME", "e2e-admin"),
        password=os.getenv("E2E_ADMIN_PASSWORD", "change-me-e2e-admin-password"),
        expected_path="/admin/operators",
    )

    text_element(driver, "Операторы")
    screenshot("presentation-11-admin-operators")

    wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='tab' and normalize-space(.)='Обучение AI']")),
    ).click()
    text_element(driver, "Результаты обучения AI", 60)
    screenshot("presentation-12-ai-models-overview")

    save_after_scroll(driver, screenshot, "Метрики на валидации", "presentation-13-model-validation-metrics")
    save_after_scroll(driver, screenshot, "Самые влиятельные признаки", "presentation-14-feature-importance")
