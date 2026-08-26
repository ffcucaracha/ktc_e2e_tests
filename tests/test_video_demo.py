from __future__ import annotations

import os
import time

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver, WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def wait(driver: WebDriver, seconds: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


def pace(seconds: float) -> None:
    """Human-readable pause for screen recording.

    DEMO_PACE scales only presentation pauses, not functional waits.
    """
    factor = max(0.1, float(os.getenv("DEMO_PACE", "1.0")))
    time.sleep(seconds * factor)


def text_element(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    return wait(driver, seconds).until(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(normalize-space(.), {xpath_literal(text)})]")),
    )


def exact_text_element(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    literal = xpath_literal(text)
    xpath = f"//*[normalize-space(.)={literal} and not(.//*[normalize-space(.)={literal}])]"
    return wait(driver, seconds).until(EC.visibility_of_element_located((By.XPATH, xpath)))


def scroll_to_text(driver: WebDriver, text: str, seconds: int = 30) -> WebElement:
    element = exact_text_element(driver, text, seconds)
    driver.execute_script(
        "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
        element,
    )
    pace(1.2)
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
    pace(2)
    driver.find_element(By.CSS_SELECTOR, "input[name='username']").send_keys(username)
    driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(password)
    pace(0.7)
    wait(driver).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()
    wait(driver).until(EC.url_contains(expected_path))
    pace(2.5)


def open_elou_simulator(driver: WebDriver) -> None:
    cards = wait(driver).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".MuiCard-root")))
    target = next((card for card in cards if "ЭЛОУ" in card.text.upper()), None)
    if target is None:
        target = next((card for card in cards if "ELOU" in card.text.upper()), None)
    if target is None:
        raise AssertionError("Карточка тренажёра ЭЛОУ не найдена")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", target)
    pace(1.5)
    target.find_element(By.XPATH, ".//a[normalize-space(.)='Открыть']").click()
    text_element(driver, "Подготовка тренировки", 30)
    pace(3.5)


def start_session(driver: WebDriver) -> None:
    start_button = wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Начать']")),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", start_button)
    pace(1.5)
    start_button.click()
    wait(driver, 60).until(EC.url_contains("/operator/sessions/"))
    text_element(driver, "AI-инструктор", 60)


def reset_process_for_clean_demo(driver: WebDriver) -> None:
    """Start the recorded interaction from a clean KTC state.

    The external simulator may retain process state/alarms from an earlier run. Reset immediately,
    before the first explanatory pause, so the video does not open on stale red alarms.
    """
    reset_button = wait(driver, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Сброс процесса']")),
    )
    reset_button.click()
    pace(2)

    # Some KTC alarms expose their own acknowledge/reset action. Clear visible stale alarms if any.
    for button in driver.find_elements(By.XPATH, "//button[normalize-space(.)='СБРОСИТЬ']"):
        if button.is_displayed() and button.is_enabled():
            button.click()
            pace(0.5)

    pace(3)


def find_clickable_equipment_button(driver: WebDriver, equipment_id: str) -> WebElement | None:
    aliases = [equipment_id]
    if equipment_id.startswith("H1"):
        aliases.append(f"Н-1{equipment_id[-1]}")

    conditions = []
    for alias in aliases:
        literal = xpath_literal(alias)
        conditions.append(f"contains(normalize-space(.), {literal})")
        conditions.append(f"contains(@aria-label, {literal})")

    buttons = driver.find_elements(By.XPATH, f"//button[({' or '.join(conditions)})]")
    return next((button for button in buttons if button.is_displayed() and button.is_enabled()), None)


def click_equipment_button(driver: WebDriver, equipment_id: str, seconds: int = 30) -> None:
    clickable = wait(driver, seconds).until(
        lambda current_driver: find_clickable_equipment_button(current_driver, equipment_id),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable)
    pace(1)
    clickable.click()
    pace(2)


def set_regulator(driver: WebDriver, regulator_id: str, value: int) -> None:
    slider = wait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, f"[aria-label='{regulator_id} valve']")),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", slider)
    pace(1)

    current = slider.get_attribute("aria-valuenow") or slider.get_attribute("value")
    if current is not None and round(float(current)) == value:
        pace(1)
        return

    slider_root = slider.find_element(By.XPATH, "./ancestor::*[contains(@class, 'MuiSlider-root')][1]")
    size = slider_root.size
    target_x = int((size["width"] * value / 100) - (size["width"] / 2))
    ActionChains(driver).move_to_element_with_offset(slider_root, target_x, 0).click().perform()

    driver.execute_script(
        """
        const input = arguments[0];
        const value = String(arguments[1]);
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        slider,
        value,
    )
    slider.send_keys(Keys.ARROW_RIGHT)
    slider.send_keys(Keys.ARROW_LEFT)
    pace(1)

    container = slider.find_element(
        By.XPATH,
        f"./ancestor::*[.//button[normalize-space(.)='Применить'] and .//*[@aria-label={xpath_literal(f'{regulator_id} valve')}]][1]",
    )
    apply_button = container.find_element(By.XPATH, ".//button[normalize-space(.)='Применить']")
    try:
        wait(driver, 20).until(lambda _: apply_button.is_enabled())
    except TimeoutException as exc:
        current = slider.get_attribute("aria-valuenow") or slider.get_attribute("value")
        if current is not None and round(float(current)) == value:
            pace(1)
            return
        raise AssertionError(
            f"Регулятор {regulator_id} не изменился до {value}; текущее значение: {current}",
        ) from exc
    apply_button.click()
    pace(2)


def demonstrate_operator_controls(driver: WebDriver) -> None:
    """Show several real controls before deliberately making a training mistake."""
    pace(3)

    # Correct beginning of the integrated procedure on the combined mnemonic.
    click_equipment_button(driver, "KR1")
    click_equipment_button(driver, "H1A")
    click_equipment_button(driver, "H1B")
    set_regulator(driver, "FRC404", 50)

    # Then show the lower ELOU control panel, which is the important second half of this simulator.
    scroll_to_text(driver, "Блок ЭЛОУ", 30)
    pace(2)
    click_equipment_button(driver, "H3")
    set_regulator(driver, "FRC408", 8)
    pace(4)


def intentional_wrong_action(driver: WebDriver) -> str:
    """Open KR6 too early to create a visually understandable sequence/process error."""
    clickable = find_clickable_equipment_button(driver, "KR6")
    if clickable is None:
        # Stable fallback if KR6 is unavailable in a particular external-simulator state.
        for equipment_id in ("H1C", "KR2", "KR3"):
            clickable = find_clickable_equipment_button(driver, equipment_id)
            if clickable is not None:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable)
                pace(1.5)
                clickable.click()
                pace(3)
                return equipment_id
        raise AssertionError("Не найдена доступная кнопка для демонстрационной ошибки")

    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable)
    pace(1.5)
    clickable.click()
    pace(3)
    return "KR6"


def wait_for_ml_warning(driver: WebDriver) -> bool:
    timeout = max(1, int(os.getenv("DEMO_AI_WARNING_WAIT_SECONDS", "35")))
    locator = (By.XPATH, "//*[contains(normalize-space(.), 'Прогноз: ERROR_IN_NEXT_10_SECONDS')]")
    try:
        element = wait(driver, timeout).until(EC.visibility_of_element_located(locator))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        pace(6)
        return True
    except TimeoutException:
        print(f"[demo] ML warning did not cross model threshold within {timeout}s; continuing", flush=True)
        pace(2)
        return False


def stop_session(driver: WebDriver) -> None:
    stop_button = wait(driver, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), 'Завершить сессию')]")),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", stop_button)
    pace(1.5)
    stop_button.click()


def wait_for_result_and_llm(driver: WebDriver) -> None:
    timeout = max(30, int(os.getenv("DEMO_RESULT_WAIT_SECONDS", "420")))
    print("[demo] CUT/ACCELERATE START: waiting for result + LLM debrief", flush=True)
    wait(driver, timeout).until(EC.url_contains("/result"))
    text_element(driver, "Итоговый разбор сессии", timeout)
    text_element(driver, "Интеллектуальный debrief", timeout)
    print("[demo] CUT/ACCELERATE END: result is ready", flush=True)
    pace(5)


def show_result_sections(driver: WebDriver) -> None:
    scroll_to_text(driver, "Timeline ключевых событий", 30)
    pace(5)
    scroll_to_text(driver, "Ошибки с объяснениями", 30)
    pace(5)
    scroll_to_text(driver, "Интеллектуальный debrief", 30)
    pace(7)
    scroll_to_text(driver, "Рекомендованная следующая тренировка", 30)
    pace(6)


def reset_browser_auth(driver: WebDriver, base_url: str) -> None:
    driver.delete_all_cookies()
    driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
    driver.get(f"{base_url}/login")
    pace(2)


def open_operator_profile(driver: WebDriver) -> None:
    username = os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator")
    row = wait(driver, 30).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//tr[@role='link'][.//td[normalize-space(.)={username!r}]]"),
        ),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", row)
    pace(2)
    row.click()
    wait(driver, 30).until(EC.url_contains("/admin/operators/"))
    text_element(driver, f"@{username}", 30)
    pace(5)

    scroll_to_text(driver, "История входов", 30)
    pace(4)
    scroll_to_text(driver, "Динамика результата", 60)
    pace(5)
    scroll_to_text(driver, "Последние тренировки", 30)
    pace(5)
    scroll_to_text(driver, "Профиль навыков", 60)
    pace(7)


def show_admin(driver: WebDriver, base_url: str) -> None:
    login(
        driver,
        base_url,
        username=os.getenv("E2E_ADMIN_USERNAME", "e2e-admin"),
        password=os.getenv("E2E_ADMIN_PASSWORD", "change-me-e2e-admin-password"),
        expected_path="/admin/operators",
    )
    text_element(driver, "Операторы", 30)
    pace(5)

    # Important admin story: inspect the exact operator whose training was just recorded.
    open_operator_profile(driver)

    # Return to the operator list and then show model transparency.
    back = wait(driver, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(normalize-space(.), 'К списку')]")),
    )
    back.click()
    wait(driver, 30).until(EC.url_contains("/admin/operators"))
    pace(3)

    ai_tab = wait(driver).until(
        EC.element_to_be_clickable((By.XPATH, "//*[@role='tab' and normalize-space(.)='Обучение AI']")),
    )
    ai_tab.click()
    text_element(driver, "Результаты обучения AI", 60)
    pace(6)
    scroll_to_text(driver, "Метрики на валидации", 30)
    pace(6)
    scroll_to_text(driver, "Самые влиятельные признаки", 30)
    pace(8)


@pytest.mark.video_demo
def test_championship_video_demo(driver: WebDriver, base_url: str) -> None:
    """Visible-browser championship walkthrough intended to be screen-recorded."""
    driver.set_window_size(1600, 900)

    login(
        driver,
        base_url,
        username=os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        password=os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
        expected_path="/operator/simulators",
    )

    text_element(driver, "Тренажёры", 30)
    pace(4)
    scroll_to_text(driver, "История прохождений", 30)
    pace(4)
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
    pace(1.5)

    open_elou_simulator(driver)
    start_session(driver)
    reset_process_for_clean_demo(driver)
    demonstrate_operator_controls(driver)

    intentional_wrong_action(driver)
    wait_for_ml_warning(driver)
    pace(3)

    stop_session(driver)
    wait_for_result_and_llm(driver)
    show_result_sections(driver)

    reset_browser_auth(driver, base_url)
    show_admin(driver, base_url)

    pace(6)
