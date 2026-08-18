from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import urllib3


class KtcApi:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._health_url = f"{self._base_url.removesuffix('/api/v1')}/health/ready"
        self._username = username
        self._password = password
        self._http = urllib3.PoolManager()
        self._token: str | None = None

    def wait_until_ready(self, timeout_seconds: float = 90) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error = "backend did not answer"

        while time.monotonic() < deadline:
            try:
                response = self._http.request(
                    "GET",
                    self._health_url,
                    timeout=urllib3.Timeout(connect=2, read=2),
                    retries=False,
                )
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
            except Exception as exc:  # noqa: BLE001 - readiness probe must tolerate startup failures
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1)

        raise RuntimeError(
            f"backend is not ready at {self._health_url} after {timeout_seconds}s: {last_error}"
        )

    def login(self) -> None:
        self.wait_until_ready()
        payload = self._request(
            "POST",
            "/auth/login",
            body={"username": self._username, "password": self._password},
            auth=False,
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AssertionError("login response does not contain access_token")
        self._token = token

    def find_simulator(self, code: str) -> dict[str, Any]:
        for item in self._request("GET", "/simulators")["items"]:
            if item.get("code") == code:
                return item
        raise AssertionError(f"simulator {code!r} not found")

    def find_scenario(self, simulator_id: str, code: str) -> dict[str, Any]:
        payload = self._request("GET", f"/simulators/{simulator_id}/scenarios")
        for item in payload["items"]:
            if item.get("code") == code:
                return item
        raise AssertionError(f"scenario {code!r} not found")

    def create_session(self, simulator_id: str, scenario_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/simulation-sessions",
            body={
                "simulator_id": simulator_id,
                "scenario_id": scenario_id,
                "mode": "training",
            },
            expected_statuses=(201,),
        )

    def send_command(
        self,
        session_id: str,
        equipment_id: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/simulation-sessions/{session_id}/commands",
            body={
                "command_id": str(uuid4()),
                "equipment_id": equipment_id,
                "action": action,
                "payload": payload or {},
                "expected_revision": None,
            },
        )

    def stop_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/simulation-sessions/{session_id}/stop")

    def assessment(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/simulation-sessions/{session_id}/assessment")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        headers = {"content-type": "application/json"}
        if auth:
            if self._token is None:
                raise RuntimeError("call login() first")
            headers["authorization"] = f"Bearer {self._token}"

        response = self._http.request(
            method,
            f"{self._base_url}{path}",
            headers=headers,
            body=json.dumps(body).encode("utf-8") if body is not None else None,
            timeout=urllib3.Timeout(connect=3, read=30),
        )
        raw = response.data.decode("utf-8")
        if response.status not in expected_statuses:
            raise AssertionError(
                f"{method} {path} returned HTTP {response.status}; body={raw[:1000]}"
            )
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise AssertionError(f"{method} {path} returned non-object JSON")
        return parsed
