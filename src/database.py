"""Read a configured file or execute a read-only MySQL SELECT."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.file_reader import read_sales_file, resolve_path


def load_target(config: dict[str, Any], base_dir: Path) -> tuple[pd.DataFrame, str]:
    target = config.get("target", {})
    mode = str(target.get("mode", "mysql")).lower()
    if mode == "file":
        path = resolve_path(base_dir, str(target["path"]))
        return read_sales_file(path), str(path)
    if mode != "mysql":
        raise ValueError("target.mode must be 'mysql' or 'file'")

    query = str(target.get("query", "")).strip()
    if not re.match(r"(?is)^select\b", query) or ";" in query.rstrip(";"):
        raise ValueError("Target query must be one read-only SELECT statement")
    database = config.get("database", {})
    user_env = str(database.get("user_env", ""))
    user = os.environ.get(user_env) if user_env else database.get("user")
    if not user:
        raise ValueError(f"Database user environment variable is unset: {user_env or '(not configured)'}")
    password_env = str(database.get("password_env", ""))
    password = os.environ.get(password_env) if password_env else None
    if not password:
        raise ValueError(
            f"Database password environment variable is unset: {password_env or '(not configured)'}"
        )

    import mysql.connector

    connection = mysql.connector.connect(
        host=database["host"],
        port=int(database.get("port", 3306)),
        database=database["database"],
        user=user,
        password=password,
        connection_timeout=int(database.get("connection_timeout", 10)),
    )
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            names = [column[0] for column in cursor.description or []]
            return pd.DataFrame(rows, columns=names), query
        finally:
            cursor.close()
    finally:
        connection.close()
