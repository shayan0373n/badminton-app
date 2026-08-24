"""
Configuration loading for the Badminton App.

Secrets come from the environment, falling back to a ``.env`` file beside this
module for local development. Deployment sets the environment directly (compose
passes the same ``.env`` through ``env_file``), so both paths read the same
file format and there is only one place to put credentials.
"""

import logging
import os
from functools import cache
from pathlib import Path

logger = logging.getLogger("app.config")

ENV_PATH = Path(__file__).parent / ".env"


@cache
def _file_secrets() -> dict[str, str]:
    """Parses the local .env once, returning an empty mapping when absent.

    Deliberately minimal, and compatible with the subset of the format Docker
    Compose accepts: ``KEY=value``, ``#`` comments, blank lines, and optional
    surrounding quotes. No interpolation and no multi-line values.
    """
    if not ENV_PATH.exists():
        return {}

    values: dict[str, str] = {}
    try:
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    except OSError as e:
        logger.warning("Could not read %s: %s", ENV_PATH, e)
        return {}

    return values


def get_secret(key: str, default: str | None = None) -> str | None:
    """Returns a secret from the environment, then .env, then default."""
    value = os.environ.get(key)
    if value is not None:
        return value
    return _file_secrets().get(key, default)


def require_secret(key: str) -> str:
    """Returns a secret, raising if it is configured nowhere.

    Raises:
        RuntimeError: If the key is absent from both the environment and .env.
    """
    value = get_secret(key)
    if value is None:
        raise RuntimeError(
            f"Missing required configuration '{key}'. Set it as an environment "
            f"variable or add it to {ENV_PATH}."
        )
    return value
