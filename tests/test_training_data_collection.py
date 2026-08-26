from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable
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
    "oil-heating-elou-integrated-startup",
    "oil-heating-elou-drainage-control",
)


@dataclass(frozen=True)
class CommandStep:
    equipment_id: str
    action: str
    payload: dict[str, object]
    delay_before_seconds: float | None = None

    def as_manifest(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "equipment_id": self.equipment_id,
            "action": self.action,
            "payload": self.payload,
        }
        if self.delay_before_seconds is not None:
            payload["delay_before_seconds"] = self.delay_before_seconds
        return payload


PlanBuilder = Callable[[random.Random], list[CommandStep]]


@dataclass(frozen=True)
class ScenarioSpec:
    simulator_code: str
    success_plan: PlanBuilder
    failure_strategies: tuple[str, ...]


def _step(equipment_id: str, action: str, value: int | float | None = None) -> CommandStep:
    payload: dict[str, object] = {} if value is None else {"value": value}
    return CommandStep(equipment_id, action, payload)


def _pump_steps(order: tuple[str, ...], action: str) -> list[CommandStep]:
    return [_step(item, action) for item in order]


def _startup_plan(rng: random.Random) -> list[CommandStep]:
    return [
        _step("KR1", "open"),
        *_pump_steps(("H1A", "H1B", "H1C"), "start"),
        _step("ND1", "start"),
        _step("ND1", "set", rng.randint(5, 30)),
    ]


def _shutdown_plan(_: random.Random) -> list[CommandStep]:
    return _pump_steps(("H1C", "H1B", "H1A"), "stop")


def _flow_control_plan(rng: random.Random) -> list[CommandStep]:
    return [
        _step("KR1", "open"),
        _step("H1A", "start"),
        _step("FRC404", "set", rng.randint(42, 58)),
        _step("FRC405", "set", rng.randint(42, 58)),
        _step("FRC406", "set", rng.randint(42, 58)),
    ]


def _sequence_plan(_: random.Random) -> list[CommandStep]:
    return [_step("KR1", "open"), *_pump_steps(("H1A", "H1B", "H1C"), "start")]


def _combined_startup_plan(rng: random.Random) -> list[CommandStep]:
    return [
        _step("KR1", "open"),
        _step("H1A", "start"),
        _step("ND1", "start"),
        _step("ND1", "set", rng.randint(5, 30)),
        _step("KR2", "open"),
        _step("KR3", "open"),
        _step("KR4", "open"),
        _step("FRC404", "set", rng.randint(45, 75)),
        _step("KR6", "open"),
        _step("FRC407", "set", rng.randint(45, 95)),
        _step("ND2", "start"),
        _step("ND2", "set", rng.randint(40, 50)),
        _step("FRC408", "set", rng.randint(5, 10)),
    ]


def _drainage_plan(_: random.Random) -> list[CommandStep]:
    return [_step("E1", "apply_voltage"), _step("KR7", "open"), _step("KR8", "open")]


SCENARIOS: dict[str, ScenarioSpec] = {
    "oil-heating-basic-startup": ScenarioSpec(
        simulator_code="oil-heating-ktc",
        success_plan=_startup_plan,
        failure_strategies=("wrong_sequence", "missed_action", "extra_action", "wrong_nd1_setpoint"),
    ),
    "oil-heating-basic-shutdown": ScenarioSpec(
        simulator_code="oil-heating-ktc",
        success_plan=_shutdown_plan,
        failure_strategies=("wrong_sequence", "missed_action", "extra_action"),
    ),
    "oil-heating-flow-control": ScenarioSpec(
        simulator_code="oil-heating-ktc",
        success_plan=_flow_control_plan,
        failure_strategies=("wrong_sequence", "missed_action", "wrong_frc_setpoint", "extra_action"),
    ),
    "oil-heating-wrong-sequence-training": ScenarioSpec(
        simulator_code="oil-heating-ktc",
        success_plan=_sequence_plan,
        failure_strategies=("wrong_sequence", "missed_action", "extra_action"),
    ),
    "oil-heating-reaction-time-training": ScenarioSpec(
        simulator_code="oil-heating-ktc",
        success_plan=_sequence_plan,
        failure_strategies=("late_action", "wrong_sequence", "missed_action"),
    ),
    "oil-heating-elou-integrated-startup": ScenarioSpec(
        simulator_code="oil-heating-elou-ktc",
        success_plan=_combined_startup_plan,
        failure_strategies=(
            "wrong_sequence",
            "missed_action",
            "wrong_frc407_setpoint",
            "wrong_nd2_setpoint",
            "wrong_frc408_setpoint",
            "early_e1_voltage",
            "extra_action",
        ),
    ),
    "oil-heating-elou-drainage-control": ScenarioSpec(
        simulator_code="oil-heating-elou-ktc",
        success_plan=_drainage_plan,
        failure_strategies=("wrong_sequence", "missed_action", "extra_action"),
    ),
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
    unknown = sorted(set(selected) - set(SCENARIOS))
    if unknown:
        raise AssertionError(f"unsupported data-collection scenarios: {', '.join(unknown)}")

    simulator_filter = os.getenv("E2E_SIMULATOR_CODE", "all").strip()
    if simulator_filter and simulator_filter != "all":
        selected = [
            scenario_code
            for scenario_code in selected
            if SCENARIOS[scenario_code].simulator_code == simulator_filter
        ]
    if not selected:
        raise AssertionError("no data-collection scenarios selected")
    return selected


def _wrong_sequence(steps: list[CommandStep], rng: random.Random) -> list[CommandStep]:
    changed = list(steps)
    first = rng.randrange(0, len(changed) - 1)
    second = rng.randrange(first + 1, len(changed))
    changed[first], changed[second] = changed[second], changed[first]
    return changed


def _missed_action(steps: list[CommandStep], rng: random.Random) -> list[CommandStep]:
    omit_index = rng.randrange(len(steps))
    return steps[:omit_index] + steps[omit_index + 1 :]


def _late_action(steps: list[CommandStep], rng: random.Random) -> list[CommandStep]:
    changed = list(steps)
    late_index = rng.randrange(len(changed))
    step = changed[late_index]
    changed[late_index] = CommandStep(
        step.equipment_id,
        step.action,
        step.payload,
        delay_before_seconds=float(os.getenv("E2E_LATE_ACTION_DELAY_SECONDS", "6.2")),
    )
    return changed


def _replace_payload(
    steps: list[CommandStep],
    equipment_ids: tuple[str, ...],
    value: int,
) -> list[CommandStep]:
    changed = list(steps)
    for index, step in enumerate(changed):
        if step.equipment_id in equipment_ids and step.action == "set":
            changed[index] = _step(step.equipment_id, "set", value)
            return changed
    raise AssertionError(f"no setpoint step found for {equipment_ids}")


def _with_extra_action(steps: list[CommandStep], scenario_code: str) -> list[CommandStep]:
    if "elou" in scenario_code:
        return [*steps, _step("H3", "start")]
    return [*steps, _step("KR5", "open")]


def _failure_plan(
    scenario_code: str,
    rng: random.Random,
) -> tuple[str, list[CommandStep], str]:
    spec = SCENARIOS[scenario_code]
    success = spec.success_plan(rng)
    strategy = rng.choice(spec.failure_strategies)

    if strategy == "wrong_sequence":
        return strategy, _wrong_sequence(success, rng), "WRONG_SEQUENCE"
    if strategy == "missed_action":
        return strategy, _missed_action(success, rng), "MISSED_ACTION"
    if strategy == "late_action":
        return strategy, _late_action(success, rng), "LATE_ACTION"
    if strategy == "wrong_nd1_setpoint":
        return strategy, _replace_payload(success, ("ND1",), rng.choice((0, 45, 80))), "WRONG_ACTION"
    if strategy == "wrong_frc_setpoint":
        return strategy, _replace_payload(success, ("FRC404", "FRC405", "FRC406"), rng.choice((20, 75))), "WRONG_ACTION"
    if strategy == "wrong_frc407_setpoint":
        return strategy, _replace_payload(success, ("FRC407",), rng.choice((10, 25))), "WRONG_ACTION"
    if strategy == "wrong_nd2_setpoint":
        return strategy, _replace_payload(success, ("ND2",), rng.choice((15, 30, 70))), "WRONG_ACTION"
    if strategy == "wrong_frc408_setpoint":
        return strategy, _replace_payload(success, ("FRC408",), rng.choice((0, 25, 60))), "WRONG_ACTION"
    if strategy == "early_e1_voltage":
        return strategy, [*success[:8], _step("E1", "apply_voltage"), *success[8:]], "WRONG_ACTION"
    if strategy == "extra_action":
        return strategy, _with_extra_action(success, scenario_code), "WRONG_ACTION"

    raise AssertionError(f"unsupported failure strategy: {strategy}")


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
        if step.delay_before_seconds is None:
            _delay(rng)
        else:
            time.sleep(step.delay_before_seconds)
        command = api.send_command(
            session_id,
            step.equipment_id,
            step.action,
            payload=step.payload,
        )
        assert command["status"] in {"accepted", "rejected"}
        api.state(session_id)

    time.sleep(float(os.getenv("E2E_SETTLE_DELAY_SECONDS", "2.2")))
    api.state(session_id)
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
    simulator_code: str,
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
            "simulator_code": simulator_code,
            "scenario_code": scenario_code,
            "session_id": session_id,
            "score": result["score"],
            "errors": [str(item["error_type"]) for item in errors],
            "steps": [step.as_manifest() for step in steps],
        }
    )


@pytest.mark.data_collection
def test_collect_training_sessions_for_all_oil_heating_scenarios() -> None:
    """Create positive and negative sessions across oil-heating and full-cycle scenarios."""
    api = KtcApi(
        os.getenv("E2E_API_BASE_URL", "http://localhost:8000/api/v1"),
        os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
    )
    api.login()

    runs = max(1, int(os.getenv("E2E_DATASET_RUNS", "5")))
    rng, seed = _rng()
    scenario_codes = _selected_scenarios()
    simulators = {
        simulator_code: api.find_simulator(simulator_code)
        for simulator_code in sorted({SCENARIOS[code].simulator_code for code in scenario_codes})
    }
    print(
        f"training-data seed={seed}; runs_per_class_per_scenario={runs}; "
        f"scenarios={','.join(scenario_codes)}"
    )

    for scenario_code in scenario_codes:
        spec = SCENARIOS[scenario_code]
        simulator = simulators[spec.simulator_code]
        simulator_id = str(simulator["id"])
        scenario = api.find_scenario(simulator_id, scenario_code)
        scenario_id = str(scenario["id"])

        for index in range(runs):
            steps = spec.success_plan(rng)
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
                simulator_code=spec.simulator_code,
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
                simulator_code=spec.simulator_code,
                scenario_code=scenario_code,
                session_id=session_id,
                result=result,
                errors=errors,
                steps=steps,
            )
