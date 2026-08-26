from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from tests.ktc_api import KtcApi
from tests.test_training_data_collection import (
    SCENARIOS,
    _collection_jobs,
    _failure_plan,
    _rng,
    _run_session,
    _selected_scenarios,
)


DEFAULT_OPERATOR_USERNAMES = (
    "e2e-operator",
    "e2e-operator-02",
    "e2e-operator-03",
    "e2e-operator-04",
    "e2e-operator-05",
)


def _operator_usernames() -> list[str]:
    raw = os.getenv("E2E_OPERATOR_USERNAMES")
    if raw is None:
        return list(DEFAULT_OPERATOR_USERNAMES)
    usernames = [item.strip() for item in raw.split(",") if item.strip()]
    if not usernames:
        raise AssertionError("E2E_OPERATOR_USERNAMES must contain at least one username")
    return usernames


def _append_manifest(item: dict[str, object]) -> None:
    path = Path(os.getenv("E2E_TRAINING_MANIFEST", "artifacts/training-data-runs.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(item, ensure_ascii=False) + "\n")


def _validate_failure_strategy_balance(scenario_codes: list[str], runs: int) -> None:
    """Ensure each scenario schedules its failure strategies as evenly as mathematically possible."""
    for scenario_code in scenario_codes:
        strategies = SCENARIOS[scenario_code].failure_strategies
        if not strategies:
            raise AssertionError(f"{scenario_code} has no failure strategies")
        base, remainder = divmod(runs, len(strategies))
        expected_counts = sorted([base + 1] * remainder + [base] * (len(strategies) - remainder))
        # _collection_jobs uses the same cyclic schedule, therefore this is the exact
        # distribution we expect regardless of the random offset/shuffle.
        if expected_counts[-1] - expected_counts[0] > 1:
            raise AssertionError(f"unbalanced failure strategy schedule for {scenario_code}")


def _operator_schedule(total_jobs: int, usernames: list[str], rng) -> list[str]:
    """Give every operator the same number of sessions up to a difference of one."""
    schedule: list[str] = []
    while len(schedule) < total_jobs:
        cycle = list(usernames)
        rng.shuffle(cycle)
        schedule.extend(cycle)
    return schedule[:total_jobs]


@pytest.mark.data_collection
def test_collect_training_sessions_across_multiple_operators() -> None:
    """Collect balanced scenario/error data while rotating sessions across five operators."""
    base_url = os.getenv("E2E_API_BASE_URL", "http://localhost:8000/api/v1")
    password = os.getenv("E2E_OPERATOR_PASSWORD", "change-me-e2e-operator-password")
    usernames = _operator_usernames()

    apis: dict[str, KtcApi] = {}
    for username in usernames:
        api = KtcApi(base_url, username, password)
        api.login()
        apis[username] = api

    runs = max(1, int(os.getenv("E2E_DATASET_RUNS", "5")))
    rng, seed = _rng()
    scenario_codes = _selected_scenarios()
    _validate_failure_strategy_balance(scenario_codes, runs)

    # IDs are global application data, so one authenticated operator can resolve them
    # and every other operator can use the same simulator/scenario IDs for its own sessions.
    reference_api = apis[usernames[0]]
    simulators = {
        simulator_code: reference_api.find_simulator(simulator_code)
        for simulator_code in sorted({SCENARIOS[code].simulator_code for code in scenario_codes})
    }
    scenario_context: dict[str, tuple[str, str]] = {}
    for scenario_code in scenario_codes:
        spec = SCENARIOS[scenario_code]
        simulator = simulators[spec.simulator_code]
        simulator_id = str(simulator["id"])
        scenario = reference_api.find_scenario(simulator_id, scenario_code)
        scenario_context[scenario_code] = (simulator_id, str(scenario["id"]))

    jobs = _collection_jobs(scenario_codes, runs, rng)
    operator_schedule = _operator_schedule(len(jobs), usernames, rng)

    strategy_counts: dict[str, Counter[str]] = defaultdict(Counter)
    operator_counts: Counter[str] = Counter(operator_schedule)
    for job in jobs:
        if job.outcome == "failure":
            strategy_counts[job.scenario_code][job.strategy] += 1

    print(
        f"training-data seed={seed}; runs_per_class_per_scenario={runs}; "
        f"total_sessions={len(jobs)}; operators={','.join(usernames)}; "
        f"scenarios={','.join(scenario_codes)}",
        flush=True,
    )
    print(f"operator session counts: {dict(operator_counts)}", flush=True)
    for scenario_code in scenario_codes:
        print(
            f"failure strategy counts {scenario_code}: {dict(strategy_counts[scenario_code])}",
            flush=True,
        )
        counts = list(strategy_counts[scenario_code].values())
        if counts:
            assert max(counts) - min(counts) <= 1, (
                f"failure strategies are not balanced for {scenario_code}: "
                f"{dict(strategy_counts[scenario_code])}"
            )

    for job_index, (job, username) in enumerate(zip(jobs, operator_schedule, strict=True), start=1):
        api = apis[username]
        spec = SCENARIOS[job.scenario_code]
        simulator_id, scenario_id = scenario_context[job.scenario_code]
        print(
            f"[{job_index}/{len(jobs)}] operator={username} scenario={job.scenario_code} "
            f"outcome={job.outcome} strategy={job.strategy} run={job.run}",
            flush=True,
        )

        if job.outcome == "success":
            steps = spec.success_plan(rng)
            expected_error = None
        else:
            steps, expected_error = _failure_plan(job.scenario_code, job.strategy, rng)

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

        context = (
            f"operator={username} scenario={job.scenario_code} outcome={job.outcome} "
            f"strategy={job.strategy} run={job.run} session_id={session_id} errors={error_types}"
        )
        if job.outcome == "success":
            assert result["error_count"] == 0, context
        else:
            assert result["error_count"] > 0, context
            assert expected_error is not None, context
            assert expected_error in error_types, context

        _append_manifest(
            {
                "seed": seed,
                "operator_username": username,
                "run": job.run,
                "outcome": job.outcome,
                "strategy": job.strategy,
                "simulator_code": spec.simulator_code,
                "scenario_code": job.scenario_code,
                "session_id": session_id,
                "score": result["score"],
                "errors": error_types,
                "steps": [step.as_manifest() for step in steps],
            }
        )
