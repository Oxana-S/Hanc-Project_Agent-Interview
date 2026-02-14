"""
Session status state machine.

Defines allowed status transitions and validation logic.
"""

from typing import Set

from .models import SessionStatus
from .exceptions import InvalidTransitionError


# State machine: allowed transitions from each status
ALLOWED_TRANSITIONS: dict[SessionStatus, Set[SessionStatus]] = {
    SessionStatus.ACTIVE: {
        SessionStatus.PAUSED,
        SessionStatus.REVIEWING,
        SessionStatus.DECLINED
    },
    SessionStatus.PAUSED: {
        SessionStatus.ACTIVE,
        SessionStatus.DECLINED
    },
    SessionStatus.REVIEWING: {
        SessionStatus.CONFIRMED,
        SessionStatus.DECLINED
    },
    SessionStatus.CONFIRMED: set(),  # Terminal state
    SessionStatus.DECLINED: set(),   # Terminal state
}


def validate_transition(from_status: SessionStatus, to_status: SessionStatus) -> None:
    """
    Validate that a status transition is allowed by the state machine.

    Args:
        from_status: Current status
        to_status: Target status

    Raises:
        InvalidTransitionError: If transition is not allowed

    Example:
        >>> validate_transition(SessionStatus.ACTIVE, SessionStatus.PAUSED)  # OK
        >>> validate_transition(SessionStatus.CONFIRMED, SessionStatus.ACTIVE)  # Raises
    """
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(
            f"Invalid transition: {from_status.value} → {to_status.value}"
        )


def is_terminal(status: SessionStatus) -> bool:
    """
    Check if a status is terminal (no outgoing transitions).

    Args:
        status: Status to check

    Returns:
        True if status is terminal (CONFIRMED or DECLINED)
    """
    return len(ALLOWED_TRANSITIONS.get(status, set())) == 0
