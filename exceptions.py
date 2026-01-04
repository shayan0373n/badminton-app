# exceptions.py
"""
Custom exceptions for the Badminton App.

This module defines domain-specific exceptions for better error handling
and debugging throughout the application.
"""


class BadmintonAppError(Exception):
    """Base exception for all application errors."""

    pass


class DatabaseError(BadmintonAppError):
    """Raised when a database operation fails."""

    pass


class SessionError(BadmintonAppError):
    """Raised when a session operation fails."""

    pass


class OptimizerError(BadmintonAppError):
    """Raised when the optimizer fails to find a solution."""

    pass


class ValidationError(BadmintonAppError):
    """Raised when input validation fails."""

    pass
