from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.ktc_api import KtcApi


DEFAULT_SCENARIOS = (
    "oil-heating-basic-startup",
    "oil-heating-basic-shutdown",
    "oil-heating-flow-control",
    "oil-heating-wrong-sequence-training",
    "oil-heating-reaction-time-training",
)


@dataclass(frozen=True)
class CommandStep:
    equipment_id: str
    action: str
    payload: dict[str, object]

    def as_manifest(self) -> dict[str, object]:
        return {
            "equipment_id": self.equipment_id,
            "action": self.action,
            "payload": self.payload,
        }


def _rng() -> tuple[random.Random, int]:
    configured = os.getenv("E2E_RANDOM_SEED")
    seed = int(configured) if configured else time.time_ns() & 0xFFFFFFFF
    return random.Random(seed), seed


def _delay(rng: random.Random) -> None:
    minimum = float(os.getenv("E2E_MIN_ACTION_DELAY_SECONDS", "0.4"))
    maximum = float(os.getenv("E2E_MAX_ACTION_DELAY_SECONDS", "1.4"))
    if maximum < minimum:
        minimum, maximum = maximum, minimum
    time.sleep(rng.uniform(minimum, maximum))


def _selected_scenarios() -> list[str]:
    raw = os.getenv("E2E_SCENARIO_CODES", ",".join(DEFAULT_SCENARIOS))
    selected = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(selected) - set(DEFAULT_SCENARIOS))
    if unknown:
        raise AssertionError(f"unsupported data-collection scenarios: {', '.join(unknown)}")
    return selected


def _pump_steps(order: tuple[str, ...], action: str) -> list[CommandStep]:
    return [CommandStep(item, action, {}) for item in order]


def _success_plan(scenario_code: str, rng: random.Random) -> list[CommandStep]:
    if scenario_code in {
        "oil-heating-basic-startup",
        "oil-heating-wrong-sequence-training",
        "oil-heating-reaction-time-training",
    }:
        return _pump_steps(("H1A", "H1B", "H1V"), "start")

    if scenario_code == "oil-heating-basic-shutdown":
        return _pump_steps(("H1V", "H1B", "H1A"), "stop")

    if scenario_code == "oil-heating-flow-control":
        return [
            CommandStep("H1A", "start", {}),
            CommandStep("FRC404", "set", {"value": rng.randint(42, 58)}),
            CommandStep("FRC405", "set", {"value": rng.randint(42, 58)}),
            CommandStep("FRC406", "set", {"value": rng.randint(42, 58)}),
        ]

    raise AssertionError(f"no success plan for {scenario_code}")


def _wrong_sequence(steps: list[CommandStep], rng: random.Random) -> list[CommandStep]:
    changed = list(steps)
    first = rng.randrange(0, len(changed) - 1)
    second = rng.randrange(first + 1, len(changed))
    changed[first], changed[second] = changed[second], changed[first]
    return changed


def _failure_plan(
    scenario_code: str,
    rng: random.Random,
) -> tuple[str, list[CommandStep], str]:
    success = _success_plan(scenario_code, rng)

    if scenario_code == "oil-heating-flow-control":
        strategy = rng.choice(("wrong_sequence", "missed_action", "wrong_setpoint"))
    else:
        strategy = rng.choice(("wrong_sequence", "missed_action", "extra_action"))

    if strategy == "wrong_sequence":
        return strategy, _wrong_sequence(success, rng), "WRONG_SEQUENCE"

    if strategy == "missed_action":
        omitted_index = rng.randrange(len(success))
        return strategy, success[:omitted_index] + success[omitted_index + 1 :], "MISSED_ACTION"

    if strategy == "wrong_setpoint":
        regulator_indexes = [
            index for index, step in enumerate(success) if step.equipment_id.startswith("FRC")
        ]
        changed_index = rng.choice(regulator_indexes)
        invalid_value = rng.choice((rng.randint(15, 35), rng.randint(65, 85)))
        changed = list(success)
        step = changed[changed_index]
        changed[changed_index] = CommandStep(step.equipment_id, step.action, {"value": invalid_value})
        return strategy, changed, "WRONG_ACTION"

    extra = success[0]
    return strategy, [*success, extra], "WRONG_ACTION"


def _append_manifest(item: dict[str, object]) -> None:
    path = Path(os.getenv("E2E_TRAINING_MANIFEST", "artifacts/training-data-runs.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(item, ensure_ascii=False) + "\n")


def _run_session(
    api: KtcApi,
    *,
    simulator_id: str,
    scenario_id: str,
    steps: list[CommandStep],
    rng: random.Random,
) -> tuple[str, dict[str, object]]:
    session = api.create_session(simulator_id, scenario_id)
    session_id = str(session["id"])

    _delay(rng)
    for step in steps:
        command = api.send_command(
            session_id,
            step.equipment_id,
            step.action,
            payload=step.payload,
        )
        assert command["status"] in {"accepted", "rejected"}
        _delay(rng)

    time.sleep(float(os.getenv("E2E_SETTLE_DELAY_SECONDS", "2.2")))
    stopped = api.stop_session(session_id)
    assert stopped["status"] == "completed"

    assessment = api.assessment(session_id)
    assert assessment["result"]["status"] == "final"
    return session_id, assessment


def _record(
    *,
    seed: int,
    run: int,
    outcome: str,
    strategy: str,
    scenario_code: str,
    session_id: str,
    result: dict[str, object],
    errors: list[dict[str, object]],
    steps: list[CommandStep],
) -> None:
    _append_manifest(
        {
            "seed": seed,
            "run": run,
            "outcome": outcome,
            "strategy": strategy,
            "scenario_code": scenario_code,
            "session_id": session_id,
            "score": result["score"],
            "errors": [str(item["error_type"]) for item in errors],
            "steps": [step.as_manifest() for step in steps],
        }
    )


@pytest.mark.data_collection
def test_collect_training_sessions_for_all_oil_heating_scenarios() -> None:
    """Create positive and negative sessions across every oil-heating training scenario."""
    api = KtcApi(
        os.getenv("E2E_API_BASE_URL", "http://localhost:8000/api/v1"),
        os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
    )
    api.login()

    simulator_code = os.getenv("E2E_SIMULATOR_CODE", "oil-heating-ktc")
    simulator = api.find_simulator(simulator_code)
    simulator_id = str(simulator["id"])

    runs = max(1, int(os.getenv("E2E_DATASET_RUNS", "5")))
    rng, seed = _rng()
    scenario_codes = _selected_scenarios()
    print(
        f"training-data seed={seed}; runs_per_class_per_scenario={runs}; "
        f"scenarios={','.join(scenario_codes)}"
    )

    for scenario_code in scenario_codes:
        scenario = api.find_scenario(simulator_id, scenario_code)
        scenario_id = str(scenario["id"])

        for index in range(runs):
            steps = _success_plan(scenario_code, rng)
            session_id, assessment = _run_session(
                api,
                simulator_id=simulator_id,
                scenario_id=scenario_id,
                steps=steps,
                rng=rng,
            )
            result = assessment["result"]
            errors = assessment["errors"]
            assert result["error_count"] == 0, errors
            _record(
                seed=seed,
                run=index + 1,
                outcome="success",
                strategy="correct_plan",
                scenario_code=scenario_code,
                session_id=session_id,
                result=result,
                errors=errors,
                steps=steps,
            )

        for index in range(runs):
            strategy, steps, expected_error = _failure_plan(scenario_code, rng)
            session_id, assessment = _run_session(
                api,
                simulator_id=simulator_id,
                scenario_id=scenario_id,
                steps=steps,
                rng=rng,
            )
            result = assessment["result"]
            errors = assessment["errors"]
            error_types = [str(item["error_type"]) for item in errors]
            assert result["error_count"] > 0
            assert expected_error in error_types, error_types
            _record(
                seed=seed,
                run=index + 1,
                outcome="failure",
                strategy=strategy,
                scenario_code=scenario_code,
                session_id=session_id,
                result=result,
                errors=errors,
                steps=steps,
            )
