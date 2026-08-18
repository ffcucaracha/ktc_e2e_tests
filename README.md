# KTC E2E tests

Небольшой отдельный проект для проверки `ktc_frontend` + `ktc_backend` и для накопления тренировочных данных.

В репозитории есть два типа проверок:

- Selenium smoke/E2E для операторского интерфейса;
- API-driven data collection tests, которые много раз проходят учебный сценарий успешно и с ошибками, чтобы backend накопил timeline, `OperatorError` и `TrainingResult` для последующего обучения ML-модели.

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

По умолчанию создаются 5 успешных и 5 неуспешных прохождений сценария `oil-heating-wrong-sequence-training`.

Успешное прохождение выполняет ожидаемую последовательность:

```text
H1A -> H1B -> H1V
```

Неуспешное прохождение случайно выбирает один из двух вариантов:

```text
wrong_sequence  -> случайная неправильная перестановка H1A/H1B/H1V
missed_action   -> пропуск одного из обязательных насосов
```

Между действиями добавляются небольшие случайные задержки. Они нужны не для искусственного создания `LATE_ACTION`, а чтобы сессии отличались по времени и server-side telemetry успевала сохранить разные snapshots.

Настройки:

```bash
E2E_DATASET_RUNS=5                 # количество успешных И неуспешных сессий
E2E_RANDOM_SEED=12345              # необязательно; если задан, прогон воспроизводим
E2E_MIN_ACTION_DELAY_SECONDS=0.4
E2E_MAX_ACTION_DELAY_SECONDS=1.4
E2E_SETTLE_DELAY_SECONDS=2.2
E2E_SIMULATOR_CODE=oil-heating-ktc
E2E_SCENARIO_CODE=oil-heating-wrong-sequence-training
```

Пример более крупного сбора:

```bash
E2E_DATASET_RUNS=25 ./scripts/collect-training-data.sh
```

Тесты пишут небольшой manifest в:

```text
artifacts/training-data-runs.jsonl
```

Там находятся только служебные сведения о прогоне: `session_id`, seed, тип прохождения, стратегия ошибки, score и error types. Сами ML-данные остаются в PostgreSQL основного приложения — именно там хранятся authoritative timeline и assessment.

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

Для набора датасета нам важны действия, которые реально проходят через application backend и сохраняются в его timeline. Использование REST API здесь быстрее и стабильнее браузера, при этом не обходит assessment или persistence слой. Selenium оставлен для проверки UI и не дублируется десятками однотипных прогонов.
