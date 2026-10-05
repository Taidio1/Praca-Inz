import json

import structlog

from src.core.logging import configure_logging


def test_configure_logging_emits_json(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging()
    structlog.get_logger().info("zdarzenie", asset="BTC")
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["event"] == "zdarzenie"
    assert payload["asset"] == "BTC"
    assert payload["level"] == "info"
    assert "timestamp" in payload
