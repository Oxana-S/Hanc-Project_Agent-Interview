"""
Custom exceptions for session management.
"""


class InvalidTransitionError(ValueError):
    """
    Raised when attempting an illegal session status transition.

    Example:
        >>> from src.session.models import SessionStatus
        >>> from src.session.status import validate_transition
        >>> validate_transition(SessionStatus.CONFIRMED, SessionStatus.ACTIVE)
        InvalidTransitionError: Invalid transition: confirmed → active
    """
    pass
