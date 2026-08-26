from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver, WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tests.ktc_api import KtcApi


Screenshot = Callable[[str], object]


def wait(driver: WebDriver, seconds: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


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


def exact_text_element(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    literal = xpath_literal(text)
    xpath = f"//*[normalize-space(.)={literal} and not(.//*[normalize-space(.)={literal}])]"
    return wait(driver, seconds).until(EC.visibility_of_element_located((By.XPATH, xpath)))


def scroll_to_element(
    driver: WebDriver,
    element: WebElement,
    *,
    block: str = "start",
    y_offset: int = 0,
) -> None:
    driver.execute_script(
        "arguments[0].scrollIntoView({block: arguments[1], inline: 'nearest'});"
        "window.scrollBy(0, arguments[2]);",
        element,
        block,
        y_offset,
    )
    time.sleep(0.5)


def scroll_to_text(
    driver: WebDriver,
    text: str,
    seconds: int = 30,
    *,
    y_offset: int = 0,
) -> WebElement:
    element = exact_text_element(driver, text, seconds)
    scroll_to_element(driver, element, y_offset=y_offset)
    return element


def save_after_scroll(
    driver: WebDriver,
    screenshot: Screenshot,
    text: str,
    name: str,
    *,
    y_offset: int = 0,
) -> None:
    scroll_to_text(driver, text, y_offset=y_offset)
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
    wait(driver).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Начать']")))


def try_intentional_wrong_action(driver: WebDriver) -> None:
    # В полном сценарии ожидаемым первым действием является KR1. H1B/H1C раньше KR1
    # дают наглядную ошибку последовательности, если кнопки присутствуют в текущей визуализации.
    for equipment_id in ("H1B", "H1C", "H1A"):
        buttons = driver.find_elements(By.CSS_SELECTOR, f"button[aria-label*='{equipment_id}']")
        clickable = next((button for button in buttons if button.is_displayed() and button.is_enabled()), None)
        if clickable is not None:
            clickable.click()
            return


def wait_for_live_ai_risk_context(driver: WebDriver) -> None:
    """Wait until the live screen shows both process risk facts and AI context.

    The CatBoost model exposes an elevated warning only when probability crosses
    the model metadata threshold. Presentation capture should not fail only because
    the current model returned, for example, 18% against a 20% threshold; in that
    case the meaningful screen is still the visible process error plus the live
    AI risk panel.
    """
    timeout = max(1, int(os.getenv("E2E_PRESENTATION_AI_WAIT_SECONDS", "75")))
    process_error_locator = (
        By.XPATH,
        "//*[contains(@class, 'MuiAlert') and "
        "(contains(normalize-space(.), 'Ошибка') or contains(normalize-space(.), 'ошибка'))]",
    )
    elevated_locator = (
        By.XPATH,
        "//*[contains(normalize-space(.), 'Прогноз: ERROR_IN_NEXT_10_SECONDS') "
        "or contains(normalize-space(.), 'Повышенный риск ошибки')]",
    )
    risk_panel_locator = (
        By.XPATH,
        "//*[contains(normalize-space(.), 'Риск ошибки:') "
        "or contains(normalize-space(.), 'Повышенный риск ошибки:')]",
    )

    wait(driver, timeout).until(EC.visibility_of_element_located(process_error_locator))
    try:
        wait(driver, timeout).until(EC.visibility_of_element_located(elevated_locator))
    except TimeoutException:
        wait(driver, 10).until(EC.visibility_of_element_located(risk_panel_locator))
        print(
            "ML elevated warning did not cross the active model threshold; "
            "capturing visible AI risk context with process error.",
            flush=True,
        )


def operator_api() -> KtcApi:
    api = KtcApi(
        os.getenv("E2E_API_BASE_URL", "http://localhost:8000/api/v1"),
        os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
    )
    api.login()
    return api


def current_session_id(driver: WebDriver) -> str:
    match = re.search(r"/operator/sessions/([^/?#]+)", driver.current_url)
    if match is None:
        raise AssertionError(f"Не удалось определить session id из URL {driver.current_url!r}")
    return match.group(1)


def send_integrated_startup_progress(api: KtcApi, session_id: str) -> None:
    """Create a partially successful session: enough correct work for a non-zero score.

    The live UI remains responsible for the visual state, while API commands make the
    assessment deterministic for presentation screenshots.
    """
    commands = [
        ("KR1", "open", {}),
        ("H1A", "start", {}),
        ("ND1", "start", {}),
        ("ND1", "set", {"value": 6}),
        ("KR2", "open", {}),
        ("KR3", "open", {}),
        ("KR4", "open", {}),
        ("FRC404", "set", {"value": 50}),
        ("KR6", "open", {}),
        ("FRC407", "set", {"value": 60}),
        ("ND2", "set", {"value": 100}),
        ("FRC408", "set", {"value": 100}),
        ("E1", "apply_voltage", {}),
    ]
    for equipment_id, action, payload in commands:
        api.send_command(session_id, equipment_id, action, payload)
        time.sleep(0.2)


def set_first_number_input(driver: WebDriver, label: str, value: str) -> None:
    field = wait(driver).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                f"(//label[normalize-space(.)={xpath_literal(label)}]/following::input[@type='number'])[1]",
            ),
        ),
    )
    field.send_keys(Keys.CONTROL, "a")
    field.send_keys(value)


def click_exact_button(driver: WebDriver, text: str, seconds: int = 30) -> None:
    wait(driver, seconds).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//button[normalize-space(.)={xpath_literal(text)}]"),
        ),
    ).click()


def open_operator_detail(driver: WebDriver, username: str) -> None:
    row = wait(driver, 30).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                f"//*[@role='link'][.//td[normalize-space(.)={xpath_literal(username)}]]",
            ),
        ),
    )
    row.click()
    text_element(driver, f"@{username}", 30)


def return_to_operator_list(driver: WebDriver) -> None:
    driver.execute_script("window.scrollTo(0, 0);")
    wait(driver, 30).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[self::a or self::button][normalize-space(.)='К списку']",
            ),
        ),
    ).click()
    wait(driver, 30).until(EC.url_contains("/admin/operators"))
    text_element(driver, "Операторы", 30)


def wait_for_complete_result_page(driver: WebDriver, timeout: int) -> None:
    """Wait for all result queries, including the potentially slow LLM debrief.

    OperatorSessionResultPage keeps the whole result page in its loading state while
    the debrief query is still pending. Waiting for both the page heading and the
    debrief section therefore prevents screenshots from being taken before the LLM
    request has finished (or the backend has returned its deterministic fallback).
    """
    text_element(driver, "Итоговый разбор сессии", timeout)
    text_element(driver, "Интеллектуальный debrief", timeout)


def stop_session_and_wait_for_result(driver: WebDriver) -> None:
    stop_button = wait(driver, 30).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(normalize-space(.), 'Завершить сессию')]"),
        ),
    )
    stop_button.click()

    # Local Ollama generation can easily take more than a minute on CPU.
    # Keep this separate from ordinary Selenium waits so presentation capture can
    # tolerate slow debrief generation without making every UI wait equally long.
    result_timeout = max(1, int(os.getenv("E2E_PRESENTATION_RESULT_WAIT_SECONDS", "300")))

    try:
        wait(driver, result_timeout).until(EC.url_contains("/result"))
        wait_for_complete_result_page(driver, result_timeout)
    except Exception:
        retry = driver.find_elements(By.XPATH, "//button[normalize-space(.)='Повторить']")
        if not retry:
            raise
        retry[0].click()
        wait_for_complete_result_page(driver, result_timeout)


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
    save_after_scroll(
        driver,
        screenshot,
        "История прохождений",
        "presentation-02-training-history",
        y_offset=140,
    )

    driver.execute_script("window.scrollTo(0, 0);")
    open_elou_simulator(driver)
    screenshot("presentation-03-elou-scenario-selection")

    click_exact_button(driver, "Начать")
    wait(driver, 60).until(EC.url_contains("/operator/sessions/"))
    text_element(driver, "AI-инструктор", 60)
    screenshot("presentation-04a-live-elou-mnemoscheme-and-ai-instructor")
    save_after_scroll(
        driver,
        screenshot,
        "Дозатор ND1",
        "presentation-04b-live-control-panel",
        y_offset=-120,
    )

    api = operator_api()
    session_id = current_session_id(driver)
    try_intentional_wrong_action(driver)
    send_integrated_startup_progress(api, session_id)
    set_first_number_input(driver, "Уставка, г/т", "100")
    click_exact_button(driver, "Задать")
    wait_for_live_ai_risk_context(driver)
    screenshot("presentation-05-live-ai-risk-and-process-error")

    stop_session_and_wait_for_result(driver)
    screenshot("presentation-06-result-summary")
    save_after_scroll(
        driver,
        screenshot,
        "Timeline ключевых событий",
        "presentation-07-timeline-ml-and-errors",
        y_offset=165,
    )
    save_after_scroll(
        driver,
        screenshot,
        "Ошибки с объяснениями",
        "presentation-08-errors-with-explanations",
        y_offset=100,
    )
    save_after_scroll(
        driver,
        screenshot,
        "Интеллектуальный debrief",
        "presentation-09-llm-debrief",
        y_offset=-110,
    )
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
    open_operator_detail(driver, os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"))
    save_after_scroll(
        driver,
        screenshot,
        "Профиль навыков",
        "presentation-12-operator-skill-profile",
        y_offset=-120,
    )

    return_to_operator_list(driver)
    wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='tab' and normalize-space(.)='Обучение AI']")),
    ).click()
    text_element(driver, "Результаты обучения AI", 60)
    screenshot("presentation-13-ai-models-overview")

    save_after_scroll(
        driver,
        screenshot,
        "Метрики на валидации",
        "presentation-14-model-validation-metrics",
        y_offset=-120,
    )
    save_after_scroll(
        driver,
        screenshot,
        "Самые влиятельные признаки",
        "presentation-15-feature-importance",
        y_offset=-120,
    )
