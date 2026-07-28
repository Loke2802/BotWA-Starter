from app.domain.automation.metrics import AutomationMetrics


def test_metrics_defaults_to_zero() -> None:
    metrics = AutomationMetrics()
    assert metrics.total_executions == 0
    assert metrics.completed == 0
    assert metrics.failed == 0
    assert metrics.cancelled == 0
    assert metrics.retries == 0


def test_metrics_with_values() -> None:
    metrics = AutomationMetrics(
        total_executions=100,
        completed=80,
        failed=15,
        cancelled=5,
        retries=10,
    )
    assert metrics.total_executions == 100
    assert metrics.completed == 80
    assert metrics.failed == 15
    assert metrics.cancelled == 5
    assert metrics.retries == 10
