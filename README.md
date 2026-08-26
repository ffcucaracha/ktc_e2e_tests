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

По умолчанию покрываются сценарии двух тренажёров: блока подогрева и полного цикла
`подогрев + ЭЛОУ`.

```text
oil-heating-basic-startup
oil-heating-basic-shutdown
oil-heating-flow-control
oil-heating-wrong-sequence-training
oil-heating-reaction-time-training
oil-heating-elou-integrated-startup
oil-heating-elou-drainage-control
```

Для каждого сценария создаются `E2E_DATASET_RUNS` успешных и столько же неуспешных прохождений. При значении по умолчанию `5` получается 70 сессий: 7 сценариев × (5 success + 5 failure).

Успешные прохождения выполняют ожидаемые действия конкретного сценария. Для `flow-control` значения FRC404/FRC405/FRC406 случайно выбираются внутри допустимого диапазона 42–58%. Для полного цикла варьируются FRC404, FRC407, ND1, ND2 и FRC408 внутри допустимых диапазонов, поэтому записи не идентичны друг другу.

Неуспешные прохождения случайно используют подходящую для сценария стратегию:

```text
wrong_sequence -> нарушение порядка шагов
missed_action  -> пропуск обязательного действия
extra_action   -> лишняя команда после выполнения ожидаемых шагов
wrong_frc_setpoint    -> FRC404/FRC405/FRC406 вне диапазона 40–60%
wrong_nd1_setpoint    -> ND1 вне диапазона 5–30 г/т
wrong_frc407_setpoint -> FRC407 вне диапазона 40–100%
wrong_nd2_setpoint    -> ND2 вне диапазона 40–50 г/т
wrong_frc408_setpoint -> FRC408 вне диапазона 5–10%
early_e1_voltage      -> подача напряжения E1 до ожидаемого шага
late_action           -> намеренная задержка больше лимита reaction-time
```

Между действиями добавляются небольшие случайные задержки. Они нужны прежде всего для разнообразия временной структуры сессий и для того, чтобы server-side telemetry успевала сохранить разные snapshots. Для сценария `reaction-time` часть неуспешных примеров создаётся намеренной задержкой, но остальные ошибки формируются через порядок, пропуски, лишние действия и неверные уставки. Это снижает риск, что модель выучит только `time_since_last_action_s`.

### Что теперь попадает в ML-признаки

Экспорт и `ai-service` используют не только старые признаки времени реакции. В датасет попадают:

```text
H1A/H1B/H1C, ND1, ND2, H3
KR1, KR6, KR7, KR8
FRC404, FRC405, FRC406, FRC407, FRC408
ND1_flow, ND1_target, ND2_flow, water_flow
FQR117-1/2/3, FQR118, oil_elou_flow_gap
PRA1, TR2, E1_level, E1_ready, E1_voltage, PO1_level
combined_scenario
recent_action_* для H1C, ND1, KR1, KR6, FRC404, FRC407, ND2, FRC408, E1, KR7, KR8
last_setpoint_* для ND1, FRC404, FRC407, ND2, FRC408
```

### Почему не включён `boiler-basic-startup`

В application backend есть ещё демонстрационный сценарий котла, но текущий ML risk feature contract построен вокруг нефтяного KTC-контура: подогрев и ЭЛОУ. Добавлять boiler-сессии в тот же набор тренировочных данных означало бы смешивать разные пространства признаков. Поэтому data collection для ML покрывает `oil-heating-ktc` и `oil-heating-elou-ktc`, а boiler остаётся отдельным UI/demo контуром.

## Настройки генератора

```bash
E2E_DATASET_RUNS=5
E2E_RANDOM_SEED=12345
E2E_MIN_ACTION_DELAY_SECONDS=0.4
E2E_MAX_ACTION_DELAY_SECONDS=1.4
E2E_LATE_ACTION_DELAY_SECONDS=6.2
E2E_SETTLE_DELAY_SECONDS=2.2
E2E_SIMULATOR_CODE=all
E2E_SCENARIO_CODES=oil-heating-basic-startup,oil-heating-basic-shutdown,oil-heating-flow-control,oil-heating-wrong-sequence-training,oil-heating-reaction-time-training,oil-heating-elou-integrated-startup,oil-heating-elou-drainage-control
```

`E2E_RANDOM_SEED` необязателен. Если его не задавать, каждый запуск получает новый seed. Если сохранить seed из вывода теста, конкретный набор случайных стратегий и setpoint можно воспроизвести.

Можно собирать только часть сценариев:

```bash
E2E_SCENARIO_CODES=oil-heating-flow-control,oil-heating-reaction-time-training \
E2E_DATASET_RUNS=10 \
./scripts/collect-training-data.sh
```

Можно ограничить сбор одним симулятором:

```bash
E2E_SIMULATOR_CODE=oil-heating-elou-ktc \
E2E_DATASET_RUNS=10 \
./scripts/collect-training-data.sh
```

Пример более крупного полного сбора:

```bash
E2E_DATASET_RUNS=25 ./scripts/collect-training-data.sh
```

Это создаст 350 сессий: 7 сценариев × (25 success + 25 failure).

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
simulator_code
score
errors
steps
```

Для сценариев с уставками в `steps` видны фактически выбранные setpoint. Сам ML dataset в этот файл не складывается: authoritative timeline и assessment остаются в PostgreSQL основного приложения.

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
