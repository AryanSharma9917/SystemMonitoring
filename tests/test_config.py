import pytest
from pydantic import ValidationError

from system_monitoring.config import Settings


def test_settings_read_prefixed_environment_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("MONITOR_ENVIRONMENT", "demo")
    monkeypatch.setenv("MONITOR_DATABASE_PATH", str(tmp_path / "configured.sqlite3"))
    monkeypatch.setenv("MONITOR_LOG_LEVEL", "WARNING")
    settings = Settings(_env_file=None)
    assert settings.environment == "demo"
    assert settings.database_path == tmp_path / "configured.sqlite3"
    assert settings.log_level == "WARNING"


@pytest.mark.parametrize(
    "values",
    [
        {"environment": "unknown"},
        {"log_level": "TRACE"},
        {"database_path": ""},
        {"database_path": ":memory:"},
    ],
)
def test_invalid_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
