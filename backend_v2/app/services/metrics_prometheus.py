from typing import Mapping


def _escape_label_value(value: object) -> str:
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _metric_fragment(name: str) -> str:
    chars = []
    for ch in str(name):
        if ch.isalnum():
            chars.append(ch.lower())
        else:
            chars.append("_")
    normalized = "".join(chars).strip("_")
    return normalized or "unknown"


def _add_header(lines: list[str], metric_name: str, metric_type: str, help_text: str) -> None:
    lines.append(f"# HELP {metric_name} {help_text}")
    lines.append(f"# TYPE {metric_name} {metric_type}")


def _append_counter(
    lines: list[str],
    metric_name: str,
    value: int | float,
    labels: Mapping[str, object] | None = None,
) -> None:
    if labels:
        label_parts = [f'{key}="{_escape_label_value(raw)}"' for key, raw in labels.items()]
        lines.append(f"{metric_name}{{{','.join(label_parts)}}} {value}")
    else:
        lines.append(f"{metric_name} {value}")


def _exclusive_histogram_to_cumulative(histogram: Mapping[str, int]) -> tuple[list[tuple[str, int]], int]:
    bounded: list[tuple[float, str, int]] = []
    overflow = int(histogram.get("inf", 0))
    for key, raw in histogram.items():
        if not key.startswith("le_"):
            continue
        boundary = key[3:]
        try:
            boundary_value = float(boundary)
        except ValueError:
            continue
        bounded.append((boundary_value, boundary, int(raw)))

    bounded.sort(key=lambda item: item[0])
    cumulative = 0
    rows: list[tuple[str, int]] = []
    for _, boundary, raw in bounded:
        cumulative += raw
        rows.append((boundary, cumulative))
    cumulative += overflow
    rows.append(("+Inf", cumulative))
    return rows, cumulative


def snapshot_to_prometheus(snapshot: Mapping[str, object], namespace: str = "ls_backend_v2") -> str:
    ns = _metric_fragment(namespace)
    lines: list[str] = []

    totals = snapshot.get("totals", {})
    if isinstance(totals, Mapping):
        for key, raw in totals.items():
            if not isinstance(raw, (int, float)):
                continue
            metric_name = f"{ns}_retrieval_{_metric_fragment(key)}_total"
            _add_header(lines, metric_name, "counter", f"Total retrieval {key}.")
            _append_counter(lines, metric_name, raw)

    strategy_counts = snapshot.get("strategy_counts", {})
    if isinstance(strategy_counts, Mapping):
        metric_name = f"{ns}_retrieval_strategy_total"
        _add_header(lines, metric_name, "counter", "Retrieval strategy usage.")
        for strategy, raw in strategy_counts.items():
            if isinstance(raw, (int, float)):
                _append_counter(lines, metric_name, raw, labels={"strategy": strategy})

    histograms = snapshot.get("histograms", {})
    if isinstance(histograms, Mapping):
        for hist_name, hist in histograms.items():
            if not isinstance(hist, Mapping):
                continue
            base = f"{ns}_retrieval_{_metric_fragment(hist_name)}"
            _add_header(lines, f"{base}_bucket", "histogram", f"Histogram buckets for {hist_name}.")
            cumulative_rows, total_count = _exclusive_histogram_to_cumulative(hist)
            for boundary, cumulative in cumulative_rows:
                _append_counter(lines, f"{base}_bucket", cumulative, labels={"le": boundary})
            _append_counter(lines, f"{base}_count", total_count)

    http_status = snapshot.get("http_status", {})
    if isinstance(http_status, Mapping):
        total = http_status.get("total")
        if isinstance(total, (int, float)):
            metric_name = f"{ns}_http_requests_total"
            _add_header(lines, metric_name, "counter", "Total HTTP requests observed by middleware.")
            _append_counter(lines, metric_name, total)

        by_class = http_status.get("by_class", {})
        if isinstance(by_class, Mapping):
            metric_name = f"{ns}_http_status_class_total"
            _add_header(lines, metric_name, "counter", "HTTP requests grouped by status class.")
            for status_class, raw in by_class.items():
                if isinstance(raw, (int, float)):
                    _append_counter(lines, metric_name, raw, labels={"class": status_class})

        by_status = http_status.get("by_status", {})
        if isinstance(by_status, Mapping):
            metric_name = f"{ns}_http_status_total"
            _add_header(lines, metric_name, "counter", "HTTP requests grouped by exact status code.")
            for status_code, raw in by_status.items():
                if isinstance(raw, (int, float)):
                    _append_counter(lines, metric_name, raw, labels={"status": status_code})

    audit_events = snapshot.get("audit_events", {})
    if isinstance(audit_events, Mapping):
        metric_name = f"{ns}_audit_event_total"
        _add_header(lines, metric_name, "counter", "Audit event counts.")
        for event, raw in audit_events.items():
            if isinstance(raw, (int, float)):
                _append_counter(lines, metric_name, raw, labels={"event": event})

    error_categories = snapshot.get("error_categories", {})
    if isinstance(error_categories, Mapping):
        metric_name = f"{ns}_error_category_total"
        _add_header(lines, metric_name, "counter", "Error counts by category.")
        for category, raw in error_categories.items():
            if isinstance(raw, (int, float)):
                _append_counter(lines, metric_name, raw, labels={"category": category})

    model_routing = snapshot.get("model_routing", {})
    if isinstance(model_routing, Mapping):
        routes = model_routing.get("routes")
        if isinstance(routes, list):
            metric_name = f"{ns}_model_route_total"
            _add_header(lines, metric_name, "counter", "Model routing outcomes by stage.")
            for route in routes:
                if not isinstance(route, Mapping):
                    continue
                count = route.get("count")
                if not isinstance(count, (int, float)):
                    continue
                _append_counter(
                    lines,
                    metric_name,
                    count,
                    labels={
                        "stage": route.get("stage", "unknown"),
                        "requested_model": route.get("requested_model", "unknown"),
                        "used_model": route.get("used_model", "unknown"),
                        "fallback": str(bool(route.get("fallback", False))).lower(),
                    },
                )

        attempt_errors = model_routing.get("attempt_errors")
        if isinstance(attempt_errors, list):
            metric_name = f"{ns}_model_attempt_error_total"
            _add_header(lines, metric_name, "counter", "Model attempt errors by stage and model.")
            for entry in attempt_errors:
                if not isinstance(entry, Mapping):
                    continue
                count = entry.get("count")
                if not isinstance(count, (int, float)):
                    continue
                _append_counter(
                    lines,
                    metric_name,
                    count,
                    labels={
                        "stage": entry.get("stage", "unknown"),
                        "model": entry.get("model", "unknown"),
                    },
                )

    model_performance = snapshot.get("model_performance", {})
    if isinstance(model_performance, Mapping):
        attempts = model_performance.get("attempts")
        if isinstance(attempts, list):
            attempt_total_name = f"{ns}_model_attempt_total"
            _add_header(lines, attempt_total_name, "counter", "Model generation attempts by stage and model.")
            latency_avg_name = f"{ns}_model_latency_ms_avg"
            _add_header(lines, latency_avg_name, "gauge", "Average model latency in milliseconds.")
            latency_p95_name = f"{ns}_model_latency_ms_p95"
            _add_header(lines, latency_p95_name, "gauge", "p95 model latency in milliseconds.")
            latency_p99_name = f"{ns}_model_latency_ms_p99"
            _add_header(lines, latency_p99_name, "gauge", "p99 model latency in milliseconds.")
            latency_max_name = f"{ns}_model_latency_ms_max"
            _add_header(lines, latency_max_name, "gauge", "Maximum model latency in milliseconds.")
            token_total_name = f"{ns}_model_tokens_total"
            _add_header(lines, token_total_name, "counter", "Model token totals by stage/model/type.")
            cost_total_name = f"{ns}_model_cost_usd_total"
            _add_header(lines, cost_total_name, "counter", "Model cost totals in USD by stage/model/type.")

            for entry in attempts:
                if not isinstance(entry, Mapping):
                    continue
                count = entry.get("count")
                if isinstance(count, (int, float)):
                    labels = {
                        "stage": entry.get("stage", "unknown"),
                        "model": entry.get("model", "unknown"),
                    }
                    _append_counter(lines, attempt_total_name, count, labels=labels)
                    _append_counter(lines, latency_avg_name, entry.get("latency_ms_avg", 0.0), labels=labels)
                    _append_counter(lines, latency_p95_name, entry.get("latency_ms_p95", 0.0), labels=labels)
                    _append_counter(lines, latency_p99_name, entry.get("latency_ms_p99", 0.0), labels=labels)
                    _append_counter(lines, latency_max_name, entry.get("latency_ms_max", 0.0), labels=labels)
                    _append_counter(lines, token_total_name, entry.get("prompt_tokens", 0), labels={**labels, "type": "prompt"})
                    _append_counter(
                        lines,
                        token_total_name,
                        entry.get("completion_tokens", 0),
                        labels={**labels, "type": "completion"},
                    )
                    _append_counter(lines, token_total_name, entry.get("total_tokens", 0), labels={**labels, "type": "total"})
                    _append_counter(
                        lines,
                        cost_total_name,
                        entry.get("estimated_input_cost_usd", 0.0),
                        labels={**labels, "type": "estimated_input"},
                    )
                    _append_counter(
                        lines,
                        cost_total_name,
                        entry.get("estimated_output_cost_usd", 0.0),
                        labels={**labels, "type": "estimated_output"},
                    )
                    _append_counter(
                        lines,
                        cost_total_name,
                        entry.get("estimated_total_cost_usd", 0.0),
                        labels={**labels, "type": "estimated_total"},
                    )
                    _append_counter(
                        lines,
                        cost_total_name,
                        entry.get("provider_reported_cost_usd", 0.0),
                        labels={**labels, "type": "provider_reported_total"},
                    )

    windowed_rates = snapshot.get("windowed_rates", {})
    if isinstance(windowed_rates, Mapping):
        for window, rates in windowed_rates.items():
            if not isinstance(rates, Mapping):
                continue
            for rate_name, raw in rates.items():
                if not isinstance(raw, (int, float)):
                    continue
                metric_name = f"{ns}_{_metric_fragment(rate_name)}"
                _add_header(lines, metric_name, "gauge", f"Windowed rate metric for {rate_name}.")
                _append_counter(lines, metric_name, raw, labels={"window": window})

    return "\n".join(lines) + "\n"
