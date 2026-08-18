# KTC E2E tests

Небольшой отдельный проект для проверки `ktc_frontend` + `ktc_backend` и для накопления тренировочных данных.

В репозитории есть два типа проверок:

- Selenium smoke/E2E для операторского интерфейса;
- API-driven data collection tests, которые много раз проходят учебные сценарии успешно и с ошибками, чтобы backend накопил timeline, `OperatorError` и `TrainingResult` для последующего обучения ML-модели.

## Обычный Selenium E2E

```bash
./scripts/run.sh
```

Он поднимает application stack из соседнего `../ktc_frontend`, запускает Chrome через Selenium и сохраняет screenshots в `artifacts/screenshots`.

Основной UI-сценарий находится в `tests/test_oil_heating_operator.py`.

## Сбор тренировочных данных

Для генерации тренировочных сессий используйте:

```bash
./scripts/collect-training-data.sh
```

По умолчанию покрываются все пять сценариев тренажёра подогрева нефти:

```text
oil-heating-basic-startup
oil-heating-basic-shutdown
oil-heating-flow-control
oil-heating-wrong-sequence-training
oil-heating-reaction-time-training
```

Для каждого сценария создаются `E2E_DATASET_RUNS` успешных и столько же неуспешных прохождений. При значении по умолчанию `5` получается 50 сессий: 5 сценариев × (5 success + 5 failure).

Успешные прохождения выполняют ожидаемые действия конкретного сценария. Для `flow-control` значения FRC404/FRC405/FRC406 случайно выбираются внутри допустимого диапазона 42–58%, поэтому успешные записи не идентичны друг другу.

Неуспешные прохождения случайно используют подходящую для сценария стратегию:

```text
wrong_sequence -> нарушение порядка шагов
missed_action  -> пропуск обязательного действия
extra_action   -> лишняя команда после выполнения ожидаемых шагов
wrong_setpoint -> значение регулятора вне диапазона 40–60% (только flow-control)
```

Между действиями добавляются небольшие случайные задержки. Они нужны прежде всего для разнообразия временной структуры сессий и для того, чтобы server-side telemetry успевала сохранить разные snapshots. Для сценария `reaction-time` эти микрозадержки намеренно остаются меньше его 5-секундного лимита в успешных прохождениях; неуспешные примеры там создаются через нарушения последовательности, пропуски и лишние действия, чтобы сбор не зависел от особенностей clock/revision конкретной версии `ktc_backend`.

### Почему не включён `boiler-basic-startup`

В application backend есть ещё демонстрационный сценарий котла, но текущий ML risk feature contract построен вокруг `oil-heating-ktc`: H1A/H1B/H1V, FRC404/FRC405/FRC406 и соответствующих process sensors. Добавлять boiler-сессии в тот же набор тренировочных данных означало бы смешивать разные пространства признаков. Поэтому data collection для ML покрывает все сценарии именно `oil-heating-ktc`, а boiler остаётся отдельным UI/demo контуром.

## Настройки генератора

```bash
E2E_DATASET_RUNS=5
E2E_RANDOM_SEED=12345
E2E_MIN_ACTION_DELAY_SECONDS=0.4
E2E_MAX_ACTION_DELAY_SECONDS=1.4
E2E_SETTLE_DELAY_SECONDS=2.2
E2E_SIMULATOR_CODE=oil-heating-ktc
E2E_SCENARIO_CODES=oil-heating-basic-startup,oil-heating-basic-shutdown,oil-heating-flow-control,oil-heating-wrong-sequence-training,oil-heating-reaction-time-training
```

`E2E_RANDOM_SEED` необязателен. Если его не задавать, каждый запуск получает новый seed. Если сохранить seed из вывода теста, конкретный набор случайных стратегий и setpoint можно воспроизвести.

Можно собирать только часть сценариев:

```bash
E2E_SCENARIO_CODES=oil-heating-flow-control,oil-heating-reaction-time-training \
E2E_DATASET_RUNS=10 \
./scripts/collect-training-data.sh
```

Пример более крупного полного сбора:

```bash
E2E_DATASET_RUNS=25 ./scripts/collect-training-data.sh
```

Это создаст 250 сессий: 5 сценариев × (25 success + 25 failure).

## Manifest

Тесты пишут небольшой manifest в:

```text
artifacts/training-data-runs.jsonl
```

В нём сохраняются служебные сведения:

```text
session_id
seed
run
outcome
strategy
scenario_code
score
errors
steps
```

Для `flow-control` в `steps` также видны фактически выбранные setpoint. Сам ML dataset в этот файл не складывается: authoritative timeline и assessment остаются в PostgreSQL основного приложения.

После накопления сессий экспорт выполняется уже из `ktc_frontend`:

```bash
cd ../ktc_frontend/backend
python -m app.commands.export_ml_sessions --output /tmp/session_exports.jsonl

cd ../ai-service
python -m scripts.generate_dataset /tmp/session_exports.jsonl datasets/risk.csv
```

## Переменные подключения

Для запуска внутри Docker используются значения по умолчанию:

```bash
E2E_BASE_URL=http://frontend:5173
E2E_API_BASE_URL=http://backend:8000/api/v1
E2E_OPERATOR_USERNAME=e2e-operator
E2E_OPERATOR_PASSWORD=change-me-e2e-operator-password
```

Для запуска API-теста с хоста можно указать:

```bash
E2E_API_BASE_URL=http://localhost:8000/api/v1 \
pytest -q -s tests/test_training_data_collection.py
```

## Почему data collection идёт через API

Для датасета важны действия, которые реально проходят через application backend и сохраняются в его timeline. REST API здесь быстрее и стабильнее браузера, но не обходит assessment или persistence layer. Selenium остаётся для проверки UI и не запускается десятки раз ради однотипного накопления данных.

Обычный `./scripts/run.sh` исключает marker `data_collection`, поэтому массовый сбор сессий запускается только явно через `./scripts/collect-training-data.sh`.
