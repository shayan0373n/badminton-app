"""
Configuration loading for the Badminton App.

Secrets are read from environment variables, falling back to
``.streamlit/secrets.toml`` so local development and the Streamlit pages keep
working without any extra setup. Nothing here imports Streamlit, which is what
lets the domain and service layers run under any front end.
"""

import logging
import os
import tomllib
from functools import cache
from pathlib import Path

logger = logging.getLogger("app.config")

SECRETS_PATH = Path(__file__).parent / ".streamlit" / "secrets.toml"


@cache
def _file_secrets() -> dict[str, str]:
    """Loads secrets.toml once, returning an empty mapping when absent."""
    if not SECRETS_PATH.exists():
        return {}
    try:
        with open(SECRETS_PATH, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        logger.warning("Could not read %s: %s", SECRETS_PATH, e)
        return {}


def get_secret(key: str, default: str | None = None) -> str | None:
    """Returns a secret from the environment, then secrets.toml, then default."""
    value = os.environ.get(key)
    if value is not None:
        return value
    return _file_secrets().get(key, default)


def require_secret(key: str) -> str:
    """Returns a secret, raising if it is configured nowhere.

    Raises:
        RuntimeError: If the key is absent from both the environment and secrets.toml.
    """
    value = get_secret(key)
    if value is None:
        raise RuntimeError(
            f"Missing required configuration '{key}'. Set it as an environment "
            f"variable or add it to {SECRETS_PATH}."
        )
    return value
