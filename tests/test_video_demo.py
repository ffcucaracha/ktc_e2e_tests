from __future__ import annotations

import os
import time

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver, WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def wait(driver: WebDriver, seconds: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def pace(seconds: float) -> None:
    """Human-readable pause for screen recording.

    DEMO_PACE scales only presentation pauses, not functional waits. Example:
    DEMO_PACE=0.8 shortens the finished video; DEMO_PACE=1.2 makes it calmer.
    """
    factor = max(0.1, float(os.getenv("DEMO_PACE", "1.0")))
    time.sleep(seconds * factor)


def text_element(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    return wait(driver, seconds).until(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(normalize-space(.), {text!r})]")),
    )


def scroll_to_text(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    element = text_element(driver, text, seconds)
    driver.execute_script(
        "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
        element,
    )
    pace(1.5)
    return element


def login(
    driver: WebDriver,
    base_url: str,
    *,
    username: str,
    password: str,
    expected_path: str,
) -> None:
    driver.get(f"{base_url}/login")
    text_element(driver, "Вход", 30)
    pace(3)
    driver.find_element(By.CSS_SELECTOR, "input[name='username']").send_keys(username)
    driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(password)
    pace(1)
    wait(driver).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()
    wait(driver).until(EC.url_contains(expected_path))
    pace(3)


def open_elou_simulator(driver: WebDriver) -> None:
    cards = wait(driver).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".MuiCard-root")))
    target = next((card for card in cards if "ЭЛОУ" in card.text.upper()), None)
    if target is None:
        target = next((card for card in cards if "ELOU" in card.text.upper()), None)
    if target is None:
        raise AssertionError("Карточка тренажёра ЭЛОУ не найдена")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", target)
    pace(2)
    target.find_element(By.XPATH, ".//a[normalize-space(.)='Открыть']").click()
    text_element(driver, "Подготовка тренировки", 30)
    pace(5)


def start_session(driver: WebDriver) -> None:
    start_button = wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Начать']")),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", start_button)
    pace(2)
    start_button.click()
    wait(driver, 60).until(EC.url_contains("/operator/sessions/"))
    text_element(driver, "AI-инструктор", 60)
    pace(6)


def intentional_wrong_action(driver: WebDriver) -> str:
    """Perform an obvious early pump action while KR1 is expected first."""
    for equipment_id in ("H1B", "H1C", "H1A"):
        buttons = driver.find_elements(By.CSS_SELECTOR, f"button[aria-label*='{equipment_id}']")
        clickable = next((button for button in buttons if button.is_displayed() and button.is_enabled()), None)
        if clickable is not None:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable)
            pace(2)
            clickable.click()
            pace(3)
            return equipment_id
    raise AssertionError("Не найдена доступная кнопка H1A/H1B/H1C для демонстрационной ошибки")


def wait_for_ml_warning(driver: WebDriver) -> bool:
    timeout = max(1, int(os.getenv("DEMO_AI_WARNING_WAIT_SECONDS", "35")))
    locator = (By.XPATH, "//*[contains(normalize-space(.), 'Прогноз: ERROR_IN_NEXT_10_SECONDS')]")
    try:
        element = wait(driver, timeout).until(EC.visibility_of_element_located(locator))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        pace(7)
        return True
    except TimeoutException:
        print(f"[demo] ML warning did not cross model threshold within {timeout}s; continuing", flush=True)
        pace(3)
        return False


def stop_session(driver: WebDriver) -> None:
    stop_button = wait(driver, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), 'Завершить сессию')]")),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", stop_button)
    pace(2)
    stop_button.click()


def wait_for_result_and_llm(driver: WebDriver) -> None:
    # This can be the long fragment that is accelerated in the final edit.
    # The normal UI loading screen stays visible while Ollama prepares the debrief.
    timeout = max(30, int(os.getenv("DEMO_RESULT_WAIT_SECONDS", "420")))
    print("[demo] CUT/ACCELERATE START: waiting for result + LLM debrief", flush=True)
    wait(driver, timeout).until(EC.url_contains("/result"))
    text_element(driver, "Итоговый разбор сессии", timeout)
    text_element(driver, "Интеллектуальный debrief", timeout)
    print("[demo] CUT/ACCELERATE END: result is ready", flush=True)
    pace(6)


def show_result_sections(driver: WebDriver) -> None:
    scroll_to_text(driver, "Timeline ключевых событий", 30)
    pace(6)
    scroll_to_text(driver, "Ошибки с объяснениями", 30)
    pace(6)
    scroll_to_text(driver, "Интеллектуальный debrief", 30)
    pace(10)
    scroll_to_text(driver, "Рекомендованная следующая тренировка", 30)
    pace(8)


def reset_browser_auth(driver: WebDriver, base_url: str) -> None:
    driver.delete_all_cookies()
    driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
    driver.get(f"{base_url}/login")
    pace(3)


def show_admin(driver: WebDriver, base_url: str) -> None:
    login(
        driver,
        base_url,
        username=os.getenv("E2E_ADMIN_USERNAME", "e2e-admin"),
        password=os.getenv("E2E_ADMIN_PASSWORD", "change-me-e2e-admin-password"),
        expected_path="/admin/operators",
    )
    text_element(driver, "Операторы", 30)
    pace(7)

    ai_tab = wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='tab' and normalize-space(.)='Обучение AI']")),
    )
    ai_tab.click()
    text_element(driver, "Результаты обучения AI", 60)
    pace(8)
    scroll_to_text(driver, "Метрики на валидации", 30)
    pace(8)
    scroll_to_text(driver, "Самые влиятельные признаки", 30)
    pace(10)


@pytest.mark.video_demo
def test_championship_video_demo(driver: WebDriver, base_url: str) -> None:
    """Paced, visible-browser walkthrough intended to be screen-recorded.

    At DEMO_PACE=1.0 the deterministic pauses contribute about 2.5-3 minutes.
    Network/model waits are separate; the Ollama wait is intentionally marked in stdout
    so that fragment can be accelerated during editing.
    """
    driver.set_window_size(1600, 1000)

    login(
        driver,
        base_url,
        username=os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        password=os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
        expected_path="/operator/simulators",
    )

    text_element(driver, "Тренажёры", 30)
    pace(6)
    scroll_to_text(driver, "История прохождений", 30)
    pace(5)
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
    pace(2)

    open_elou_simulator(driver)
    start_session(driver)

    intentional_wrong_action(driver)
    wait_for_ml_warning(driver)
    pace(4)

    stop_session(driver)
    wait_for_result_and_llm(driver)
    show_result_sections(driver)

    reset_browser_auth(driver, base_url)
    show_admin(driver, base_url)

    # Keep the final ML transparency screen on camera before Chrome closes.
    pace(8)
