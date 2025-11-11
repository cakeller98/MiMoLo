import time

from mimolo.core.runtime import PluginErrorTracker, PluginScheduler


def test_plugin_scheduler_should_poll_and_reset() -> None:
    sch = PluginScheduler()
    label = "x"
    t0 = time.time()
    # First call should poll
    assert sch.should_poll(label, 0.01, t0) is True
    # Immediately again should not
    assert sch.should_poll(label, 10.0, t0) is False
    # After reset, should poll again
    sch.reset(label)
    assert sch.should_poll(label, 10.0, t0) is True


def test_error_tracker_backoff_and_quarantine() -> None:
    tr = PluginErrorTracker(base_backoff_s=0.1, max_backoff_s=0.2)
    label = "p"
    assert tr.is_quarantined(label) is False
    tr.record_error(label)
    assert tr.is_quarantined(label) is True
    # After a brief sleep longer than max backoff, quarantine should clear
    time.sleep(0.25)
    assert tr.is_quarantined(label) is False
    tr.record_success(label)
    assert tr.is_quarantined(label) is False
