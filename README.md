# KTC Selenium E2E

Separate Selenium E2E project for `ktc_frontend` + external `ktc_backend` integration.

The tests do not modify `ktc_backend`. They start the application stack from
`../ktc_frontend/docker-compose.yml`, run Chrome through Selenium, and save
screenshots to `artifacts/screenshots`.

## Run

From this directory:

```bash
./scripts/run.sh
```

Useful variables:

```bash
E2E_BASE_URL=http://frontend:5173
E2E_OPERATOR_USERNAME=e2e-operator
E2E_OPERATOR_PASSWORD=change-me-e2e-operator-password
E2E_SCREENSHOT_DIR=artifacts/screenshots
```

## Scenario

`tests/test_oil_heating_operator.py` covers the minimal operator flow:

1. Log in as operator.
2. Open the simulator catalog.
3. Choose the `oil-heating-v1` simulator.
4. Start a training session.
5. Start pumps `H1A`, `H1B`, `H1V`.
6. Move `FRC404`, `FRC405`, `FRC406` sliders.
7. Wait longer than the UI polling interval and assert slider values do not reset.
8. Apply valve values and assert the backend snapshot appears in the UI.

Screenshots are saved for each major step and again on test failure.
