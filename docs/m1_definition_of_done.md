# M1 Definition of Done (Backend V2 Foundations)

Stand: 19 February 2026

## Scope
M1 covers the "Fundament und Qualitaetsgates" phase for `backend_v2`.

## Mandatory acceptance criteria
- `backend_v2_tests` GitHub Action is green on every PR.
- `codecov/patch` is reported and green on every PR.
- Test command in CI enforces `--cov-fail-under=70`.
- Key config paths are covered by tests (`env`, `fallback`, error path).
- Provider and orchestrator failure paths are covered by tests.
- API smoke flow is covered (`/`, `/v2/health`, `/v2/game/turn`).
- Branch protection requires at least:
  - `backend_v2_tests`
  - `codecov/patch`

## Known constraint (current)
- `codecov/project` is currently not required, because the check is not consistently reported for this repository setup.
- Decision: Continue with `codecov/patch` as the blocking quality gate until `codecov/project` reporting is stable.

## Evidence checklist
- CI workflow file: `.github/workflows/backend_v2_ci.yml`
- Codecov config file: `codecov.yml`
- Tests:
  - `backend_v2/tests/test_config.py`
  - `backend_v2/tests/test_openrouter_provider.py`
  - `backend_v2/tests/test_orchestrator.py`
  - `backend_v2/tests/test_main_api.py`

## Exit criteria for moving to M2
- 2 consecutive PRs merged with green required checks.
- No flaky test reruns needed in those PRs.
- Coverage stays >= 70% after merge to `main`.
- Team confirms M2 scope freeze (persistence + auth + observability baseline).
