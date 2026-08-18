from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

import pytest

from tests.ktc_api import KtcApi


CORRECT_SEQUENCE = ("H1A", "H1B", "H1V")


def _rng() -> tuple[random.Random, int]:
    configured = os.getenv("E2E_RANDOM_SEED")
    seed = int(configured) if configured else time.time_ns() & 0xFFFFFFFF
    return random.Random(seed), seed


def _delay(rng: random.Random) -> None:
    minimum = float(os.getenv("E2E_MIN_ACTION_DELAY_SECONDS", "0.4"))
    maximum = float(os.getenv("E2E_MAX_ACTION_DELAY_SECONDS", "1.4"))
    time.sleep(rng.uniform(minimum, maximum))


def _bad_plan(rng: random.Random) -> tuple[str, list[str], str]:
    strategy = rng.choice(("wrong_sequence", "missed_action"))
    if strategy == "wrong_sequence":
        sequence = list(CORRECT_SEQUENCE)
        while tuple(sequence) == CORRECT_SEQUENCE:
            rng.shuffle(sequence)
        return strategy, sequence, "WRONG_SEQUENCE"

    omitted = rng.choice(CORRECT_SEQUENCE)
    sequence = [pump for pump in CORRECT_SEQUENCE if pump != omitted]
    return strategy, sequence, "MISSED_ACTION"


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
    sequence: list[str] | tuple[str, ...],
    rng: random.Random,
) -> tuple[str, dict[str, object]]:
    session = api.create_session(simulator_id, scenario_id)
    session_id = str(session["id"])

    _delay(rng)
    for equipment_id in sequence:
        command = api.send_command(session_id, equipment_id, "start")
        assert command["status"] in {"accepted", "rejected"}
        _delay(rng)

    time.sleep(float(os.getenv("E2E_SETTLE_DELAY_SECONDS", "2.2")))
    stopped = api.stop_session(session_id)
    assert stopped["status"] == "completed"

    assessment = api.assessment(session_id)
    assert assessment["result"]["status"] == "final"
    return session_id, assessment


@pytest.mark.data_collection
def test_collect_balanced_training_sessions() -> None:
    """Create successful and intentionally flawed sessions for later ML export."""
    api = KtcApi(
        os.getenv("E2E_API_BASE_URL", "http://localhost:8000/api/v1"),
        os.getenv("E2E_OPERATOR_USERNAME", "e2e-operator"),
        os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password"),
    )
    api.login()

    simulator_code = os.getenv("E2E_SIMULATOR_CODE", "oil-heating-ktc")
    scenario_code = os.getenv(
        "E2E_SCENARIO_CODE",
        "oil-heating-wrong-sequence-training",
    )
    simulator = api.find_simulator(simulator_code)
    scenario = api.find_scenario(str(simulator["id"]), scenario_code)

    runs = max(1, int(os.getenv("E2E_DATASET_RUNS", "5")))
    rng, seed = _rng()
    print(f"training-data seed={seed}; runs_per_class={runs}")

    for index in range(runs):
        session_id, assessment = _run_session(
            api,
            simulator_id=str(simulator["id"]),
            scenario_id=str(scenario["id"]),
            sequence=CORRECT_SEQUENCE,
            rng=rng,
        )
        result = assessment["result"]
        errors = assessment["errors"]
        assert result["error_count"] == 0, errors
        _append_manifest(
            {
                "seed": seed,
                "run": index + 1,
                "outcome": "success",
                "strategy": "correct_sequence",
                "scenario_code": scenario_code,
                "session_id": session_id,
                "score": result["score"],
                "errors": [],
            }
        )

    for index in range(runs):
        strategy, sequence, expected_error = _bad_plan(rng)
        session_id, assessment = _run_session(
            api,
            simulator_id=str(simulator["id"]),
            scenario_id=str(scenario["id"]),
            sequence=sequence,
            rng=rng,
        )
        result = assessment["result"]
        errors = assessment["errors"]
        error_types = [str(item["error_type"]) for item in errors]
        assert result["error_count"] > 0
        assert expected_error in error_types, error_types
        _append_manifest(
            {
                "seed": seed,
                "run": index + 1,
                "outcome": "failure",
                "strategy": strategy,
                "sequence": sequence,
                "scenario_code": scenario_code,
                "session_id": session_id,
                "score": result["score"],
                "errors": error_types,
            }
        )
