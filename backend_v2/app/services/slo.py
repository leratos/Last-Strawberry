from typing import Mapping


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_slo(
    *,
    snapshot: Mapping[str, object],
    window: str,
    max_5xx_percent: float,
    max_429_percent: float,
) -> dict[str, object]:
    windowed_rates = snapshot.get("windowed_rates", {})
    if not isinstance(windowed_rates, Mapping):
        windowed_rates = {}

    selected_window = windowed_rates.get(window, {})
    if not isinstance(selected_window, Mapping):
        selected_window = {}

    errors_5xx_percent = _to_float(selected_window.get("errors_5xx_percent"), default=0.0)
    rate_limit_429_percent = _to_float(selected_window.get("rate_limit_429_percent"), default=0.0)

    breaches: list[str] = []
    if errors_5xx_percent > float(max_5xx_percent):
        breaches.append("errors_5xx_percent")
    if rate_limit_429_percent > float(max_429_percent):
        breaches.append("rate_limit_429_percent")

    status = "breach" if breaches else "ok"

    return {
        "status": status,
        "window": window,
        "thresholds": {
            "max_5xx_percent": float(max_5xx_percent),
            "max_429_percent": float(max_429_percent),
        },
        "actual": {
            "errors_5xx_percent": round(errors_5xx_percent, 2),
            "rate_limit_429_percent": round(rate_limit_429_percent, 2),
        },
        "breaches": breaches,
    }
