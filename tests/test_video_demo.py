from __future__ import annotations

import os
import time

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver, WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ML_WARNING_TEXT = "Прогноз: ERROR_IN_NEXT_10_SECONDS"


def wait(driver: WebDriver, seconds: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def pace(seconds: float) -> None:
    """Human-readable pause for screen recording.

    DEMO_PACE scales only presentation pauses, not functional waits.
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
    """Start the recorded interaction from a clean KTC state."""
    reset_button = wait(driver, 30).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Сброс процесса']")),
    )
    reset_button.click()
    pace(2)

    for button in driver.find_elements(By.XPATH, "//button[normalize-space(.)='СБРОСИТЬ']"):
        if button.is_displayed() and button.is_enabled():
            button.click()
            pace(0.5)

    pace(3)


def click_equipment_button(driver: WebDriver, equipment_id: str, *, pause_after: float = 1.8) -> None:
    buttons = driver.find_elements(
        By.XPATH,
        f"//button[contains(normalize-space(.), '{equipment_id}') and not(@disabled)]",
    )
    clickable = next((button for button in buttons if button.is_displayed() and button.is_enabled()), None)
    if clickable is None:
        raise AssertionError(f"Не найдена доступная кнопка {equipment_id}")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable)
    pace(0.8)
    clickable.click()
    pace(pause_after)


def set_regulator(driver: WebDriver, regulator_id: str, value: int) -> None:
    slider = wait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, f"[aria-label='{regulator_id} valve']")),
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", slider)
    pace(0.8)
    slider.send_keys(Keys.HOME)
    for _ in range(value):
        slider.send_keys(Keys.ARROW_RIGHT)
    pace(0.6)

    container = slider.find_element(By.XPATH, "./ancestor::div[contains(@class, 'MuiBox-root')][1]")
    apply_button = container.find_element(By.XPATH, ".//button[normalize-space(.)='Применить']")
    wait(driver, 20).until(lambda _: apply_button.is_enabled())
    apply_button.click()
    pace(1.8)


def set_dosing(
    driver: WebDriver,
    *,
    field_label: str,
    value: int,
    section_title: str,
    start_after_set: bool,
) -> None:
    label = wait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, f"//label[normalize-space(.)={field_label!r}]")),
    )
    input_id = label.get_attribute("for")
    if not input_id:
        raise AssertionError(f"Поле {field_label} не связано с input")
    field = driver.find_element(By.ID, input_id)
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", field)
    pace(0.8)
    field.send_keys(Keys.CONTROL, "a")
    field.send_keys(str(value))

    section = field.find_element(By.XPATH, "./ancestor::div[contains(@class, 'MuiBox-root')][1]")
    # If the nearest MUI box is the TextField itself, climb until the dosing title is in the container.
    for _ in range(5):
        if section_title in section.text and "Задать" in section.text:
            break
        section = section.find_element(By.XPATH, "..")
    else:
        raise AssertionError(f"Не найден контейнер {section_title}")

    set_button = section.find_element(By.XPATH, ".//button[normalize-space(.)='Задать']")
    wait(driver, 20).until(lambda _: set_button.is_enabled())
    set_button.click()
    pace(1.4)

    if start_after_set:
        start_buttons = section.find_elements(By.XPATH, ".//button[normalize-space(.)='Пуск']")
        start_button = next((item for item in start_buttons if item.is_displayed() and item.is_enabled()), None)
        if start_button is not None:
            start_button.click()
            pace(1.8)


def ml_warning_element(driver: WebDriver) -> WebElement | None:
    elements = driver.find_elements(By.XPATH, f"//*[contains(normalize-space(.), {ML_WARNING_TEXT!r})]")
    return next((item for item in elements if item.is_displayed()), None)


def show_ml_prediction(driver: WebDriver, seconds: int = 6) -> bool:
    """If the model has already crossed its configured threshold, put the warning on camera."""
    element = ml_warning_element(driver)
    if element is None:
        return False
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
    print("[demo] ML prediction visible BEFORE intentional error", flush=True)
    pace(seconds)
    return True


def wait_for_ml_prediction(driver: WebDriver) -> bool:
    timeout = max(5, int(os.getenv("DEMO_AI_WARNING_WAIT_SECONDS", "60")))
    locator = (By.XPATH, f"//*[contains(normalize-space(.), {ML_WARNING_TEXT!r})]")
    print(f"[demo] waiting up to {timeout}s for ML prediction before creating the demo error", flush=True)
    try:
        element = wait(driver, timeout).until(EC.visibility_of_element_located(locator))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        print("[demo] ML prediction visible BEFORE intentional error", flush=True)
        pace(7)
        return True
    except TimeoutException:
        print(f"[demo] ML prediction did not cross the active threshold within {timeout}s", flush=True)
        return False


def intentional_extra_action(driver: WebDriver) -> None:
    """Create one isolated, recoverable training error after ML has warned.

    H3 is an explicit extra-action failure strategy for the integrated ELOU startup dataset.
    It does not replace an expected procedure step, so the correct plan can continue afterwards
    and the operator still finishes with a credible score instead of 0/100.
    """
    click_equipment_button(driver, "H3", pause_after=2.5)


def run_integrated_startup_with_prediction(driver: WebDriver) -> None:
    """Perform the real integrated-startup procedure and inject only one ML-anticipated error."""
    error_created = False

    def after_correct_step() -> None:
        nonlocal error_created
        if error_created:
            return
        # Give realtime telemetry/AI a short opportunity to update after each valid command.
        pace(1.0)
        if show_ml_prediction(driver, seconds=4):
            intentional_extra_action(driver)
            error_created = True

    # Exact success plan used by the ML dataset collector for oil-heating-elou-integrated-startup.
    click_equipment_button(driver, "KR1")
    after_correct_step()

    click_equipment_button(driver, "H1A")
    after_correct_step()

    set_dosing(
        driver,
        field_label="Уставка, г/т",
        value=15,
        section_title="Дозатор ND1",
        start_after_set=True,
    )
    after_correct_step()

    for valve_id in ("KR2", "KR3", "KR4"):
        click_equipment_button(driver, valve_id)
        after_correct_step()

    set_regulator(driver, "FRC404", 60)
    after_correct_step()

    click_equipment_button(driver, "KR6")
    after_correct_step()

    set_regulator(driver, "FRC407", 60)
    after_correct_step()

    set_dosing(
        driver,
        field_label="Щелочь, г/т",
        value=45,
        section_title="Дозатор ND2",
        start_after_set=True,
    )
    after_correct_step()

    set_regulator(driver, "FRC408", 8)
    after_correct_step()

    # Prefer the honest presentation: prediction must be visible before we intentionally err.
    # If it has not happened during normal procedure, wait on the completed, otherwise-correct state.
    if not error_created:
        if not wait_for_ml_prediction(driver):
            raise AssertionError(
                "ML did not predict an error during the demo. Rerun the recording rather than "
                "submitting a video where the claimed predictive warning is absent."
            )
        intentional_extra_action(driver)
        error_created = True

    # Show the post-error state briefly, while preserving the fact that the warning was shown first.
    driver.execute_script("window.scrollTo({top: 160, behavior: 'smooth'});")
    pace(5)


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

    open_operator_profile(driver)

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

    # Run the real procedure, let the model warn first, then make exactly one deliberate mistake.
    run_integrated_startup_with_prediction(driver)

    stop_session(driver)
    wait_for_result_and_llm(driver)
    show_result_sections(driver)

    reset_browser_auth(driver, base_url)
    show_admin(driver, base_url)

    pace(6)
