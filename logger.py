# logger.py
"""
Logging configuration for the Badminton App.

This module provides centralized logging setup. The setup_logging() function
should be called once at application startup (e.g., in main.py or 1_Setup.py).

All app modules should use the "app" namespace:
    import logging
    logger = logging.getLogger("app.module_name")

This keeps third-party library logs quiet while allowing granular control
over the app's own logging level via the LOG_LEVEL environment variable.
"""

import logging
import sys

# App namespace prefix - all app loggers should use this
APP_LOGGER_NAME = "app"


def setup_logging(app_level: int = logging.INFO) -> None:
    """
    Configure logging for the application.

    - Root logger is set to WARNING (keeps third-party libraries quiet)
    - App namespace logger ("app.*") is set to the specified level

    This should be called ONCE at application startup (entry point).

    Args:
        app_level: The logging level for app modules (default: INFO)
    """
    # Configure root logger to WARNING - silences third-party library noise
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    # Avoid adding duplicate handlers if setup is called multiple times
    if not root_logger.handlers:
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)  # Handler accepts all; loggers filter

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)

        root_logger.addHandler(handler)

    # Configure the app namespace logger
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(app_level)


def log_optimizer_debug(
    logger: logging.Logger,
    num_courts: int,
    max_rating_on_court: dict,
    min_rating_on_court: dict,
    total_skill_objective: float,
    total_pairing_objective: float,
    objective_value: float,
    max_team_power: dict | None = None,
    min_team_power: dict | None = None,
    total_power_objective: float | None = None,
) -> None:
    """
    Log optimizer debug information in a consistent format.

    Args:
        logger: Logger instance to use
        num_courts: Number of courts
        max_rating_on_court: Dict of max ratings per court
        min_rating_on_court: Dict of min ratings per court
        total_skill_objective: Total skill objective value
        total_pairing_objective: Total pairing objective value
        objective_value: Final objective value
        max_team_power: Optional dict of max team power per court (doubles only)
        min_team_power: Optional dict of min team power per court (doubles only)
        total_power_objective: Optional total power objective (doubles only)
    """
    logger.debug(
        "Max Rating on Court: %s",
        {c: max_rating_on_court[c].value() for c in range(num_courts)},
    )
    logger.debug(
        "Min Rating on Court: %s",
        {c: min_rating_on_court[c].value() for c in range(num_courts)},
    )

    if max_team_power is not None:
        logger.debug(
            "Max Team Power: %s",
            {c: max_team_power[c].value() for c in range(num_courts)},
        )
    if min_team_power is not None:
        logger.debug(
            "Min Team Power: %s",
            {c: min_team_power[c].value() for c in range(num_courts)},
        )

    logger.debug("Total Skill Objective: %s", total_skill_objective)
    if total_power_objective is not None:
        logger.debug("Total Power Objective: %s", total_power_objective)
    logger.debug("Total Pairing Objective: %s", total_pairing_objective)
    logger.debug("Objective Value: %s", objective_value)
