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
