"""
Unit tests for session status state machine.

Tests the SessionStatus enum, RuntimeStatus enum, and state machine
transition validation logic.
"""

import pytest

from src.session.models import SessionStatus, RuntimeStatus
from src.session.status import validate_transition, is_terminal, ALLOWED_TRANSITIONS
from src.session.exceptions import InvalidTransitionError


class TestSessionStatusEnum:
    """Tests for SessionStatus enum."""

    def test_all_statuses_defined(self):
        """All 5 persistent statuses are defined."""
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.PAUSED.value == "paused"
        assert SessionStatus.REVIEWING.value == "reviewing"
        assert SessionStatus.CONFIRMED.value == "confirmed"
        assert SessionStatus.DECLINED.value == "declined"

    def test_enum_count(self):
        """Exactly 5 persistent statuses exist."""
        assert len(SessionStatus) == 5


class TestRuntimeStatusEnum:
    """Tests for RuntimeStatus enum."""

    def test_all_statuses_defined(self):
        """All 5 runtime statuses are defined."""
        assert RuntimeStatus.IDLE.value == "idle"
        assert RuntimeStatus.PROCESSING.value == "processing"
        assert RuntimeStatus.COMPLETING.value == "completing"
        assert RuntimeStatus.COMPLETED.value == "completed"
        assert RuntimeStatus.ERROR.value == "error"

    def test_enum_count(self):
        """Exactly 5 runtime statuses exist."""
        assert len(RuntimeStatus) == 5


class TestStateMachine:
    """Tests for state machine transition validation."""

    def test_active_to_paused_allowed(self):
        """Active → Paused transition is allowed."""
        # Should not raise
        validate_transition(SessionStatus.ACTIVE, SessionStatus.PAUSED)

    def test_active_to_reviewing_allowed(self):
        """Active → Reviewing transition is allowed."""
        validate_transition(SessionStatus.ACTIVE, SessionStatus.REVIEWING)

    def test_active_to_declined_allowed(self):
        """Active → Declined transition is allowed."""
        validate_transition(SessionStatus.ACTIVE, SessionStatus.DECLINED)

    def test_paused_to_active_allowed(self):
        """Paused → Active transition is allowed."""
        validate_transition(SessionStatus.PAUSED, SessionStatus.ACTIVE)

    def test_paused_to_declined_allowed(self):
        """Paused → Declined transition is allowed."""
        validate_transition(SessionStatus.PAUSED, SessionStatus.DECLINED)

    def test_reviewing_to_confirmed_allowed(self):
        """Reviewing → Confirmed transition is allowed."""
        validate_transition(SessionStatus.REVIEWING, SessionStatus.CONFIRMED)

    def test_reviewing_to_declined_allowed(self):
        """Reviewing → Declined transition is allowed."""
        validate_transition(SessionStatus.REVIEWING, SessionStatus.DECLINED)

    def test_confirmed_to_active_forbidden(self):
        """Confirmed → Active transition is forbidden (terminal state)."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(SessionStatus.CONFIRMED, SessionStatus.ACTIVE)
        assert "Invalid transition: confirmed → active" in str(exc_info.value)

    def test_declined_to_active_forbidden(self):
        """Declined → Active transition is forbidden (terminal state)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(SessionStatus.DECLINED, SessionStatus.ACTIVE)

    def test_active_to_confirmed_forbidden(self):
        """Active → Confirmed is forbidden (must go through Reviewing)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(SessionStatus.ACTIVE, SessionStatus.CONFIRMED)

    def test_paused_to_reviewing_forbidden(self):
        """Paused → Reviewing is forbidden (must resume first)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(SessionStatus.PAUSED, SessionStatus.REVIEWING)

    def test_all_active_transitions(self):
        """All valid transitions from Active work."""
        validate_transition(SessionStatus.ACTIVE, SessionStatus.PAUSED)
        validate_transition(SessionStatus.ACTIVE, SessionStatus.REVIEWING)
        validate_transition(SessionStatus.ACTIVE, SessionStatus.DECLINED)

    def test_all_paused_transitions(self):
        """All valid transitions from Paused work."""
        validate_transition(SessionStatus.PAUSED, SessionStatus.ACTIVE)
        validate_transition(SessionStatus.PAUSED, SessionStatus.DECLINED)

    def test_all_reviewing_transitions(self):
        """All valid transitions from Reviewing work."""
        validate_transition(SessionStatus.REVIEWING, SessionStatus.CONFIRMED)
        validate_transition(SessionStatus.REVIEWING, SessionStatus.DECLINED)

    def test_terminal_states_have_no_outgoing_transitions(self):
        """Confirmed and Declined have no valid outgoing transitions."""
        for status in [SessionStatus.CONFIRMED, SessionStatus.DECLINED]:
            for target in SessionStatus:
                if target != status:  # Self-transition is pointless but technically not enforced
                    with pytest.raises(InvalidTransitionError):
                        validate_transition(status, target)


class TestTerminalCheck:
    """Tests for is_terminal() helper function."""

    def test_confirmed_is_terminal(self):
        """Confirmed status is terminal."""
        assert is_terminal(SessionStatus.CONFIRMED) is True

    def test_declined_is_terminal(self):
        """Declined status is terminal."""
        assert is_terminal(SessionStatus.DECLINED) is True

    def test_active_not_terminal(self):
        """Active status is not terminal."""
        assert is_terminal(SessionStatus.ACTIVE) is False

    def test_paused_not_terminal(self):
        """Paused status is not terminal."""
        assert is_terminal(SessionStatus.PAUSED) is False

    def test_reviewing_not_terminal(self):
        """Reviewing status is not terminal."""
        assert is_terminal(SessionStatus.REVIEWING) is False


class TestStateMachineCompleteness:
    """Meta-tests to ensure state machine is fully specified."""

    def test_all_statuses_have_transition_rules(self):
        """Every SessionStatus has an entry in ALLOWED_TRANSITIONS."""
        for status in SessionStatus:
            assert status in ALLOWED_TRANSITIONS

    def test_allowed_transitions_only_use_valid_statuses(self):
        """ALLOWED_TRANSITIONS only references valid SessionStatus values."""
        for status, allowed in ALLOWED_TRANSITIONS.items():
            assert isinstance(status, SessionStatus)
            for target in allowed:
                assert isinstance(target, SessionStatus)
