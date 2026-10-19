import json

from system_monitoring.logging import JsonFormatter


def test_request_logs_use_templates_and_omit_query_values(client, caplog):
    client.get("/health?token=private-token", headers={"Authorization": "Bearer secret"})
    entries = [json.loads(JsonFormatter().format(record)) for record in caplog.records]
    request = next(entry for entry in entries if entry["message"] == "Request completed")
    assert request["route"] == "/health"
    assert request["status_code"] == 200
    assert "request_id" in request
    assert "duration_ms" in request
    assert "private-token" not in json.dumps(entries)
    assert "Bearer secret" not in json.dumps(entries)


def test_formatter_encodes_untrusted_text_as_one_json_record():
    import logging

    record = logging.LogRecord(
        "system_monitoring", logging.WARNING, "", 0, "first\nsecond", (), None
    )
    formatted = JsonFormatter().format(record)
    assert len(formatted.splitlines()) == 1
    assert json.loads(formatted)["message"] == "first\nsecond"
