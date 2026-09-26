"""Shared template helpers."""

from datetime import UTC, datetime

from family_assistant.templating import local


def test_local_converts_aware_timestamps_to_local_time() -> None:
    utc = datetime(2026, 9, 26, 23, 35, tzinfo=UTC)
    shown = local(utc)
    assert shown == utc  # same instant
    assert shown.tzinfo == utc.astimezone().tzinfo  # expressed in the system zone


def test_local_keeps_naive_values() -> None:
    naive = datetime(2026, 9, 26, 19, 35)
    assert local(naive) is naive
