import pytest

from src.database import load_target


def test_database_rejects_non_select_queries(tmp_path):
    config = {"target": {"mode": "mysql", "query": "DELETE FROM fact_sales"}}

    with pytest.raises(ValueError, match="read-only SELECT"):
        load_target(config, tmp_path)


def test_database_requires_environment_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_DB_USER", raising=False)
    config = {
        "target": {"mode": "mysql", "query": "SELECT 1"},
        "database": {
            "user_env": "TEST_DB_USER",
            "password_env": "TEST_DB_PASSWORD",
        },
    }

    with pytest.raises(ValueError, match="user environment variable is unset"):
        load_target(config, tmp_path)
