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


def test_secret_values_are_not_echoed_in_configuration_errors():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, admin_password="tiny")
    assert "tiny" not in str(error.value)


def test_production_requires_https_cookies():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", secure_cookies=False)
    assert Settings(_env_file=None, environment="production", secure_cookies=True).secure_cookies
