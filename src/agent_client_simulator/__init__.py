"""
Simulation framework for testing ConsultantInterviewer.

Reusable components:
- SimulatedClient: AI-powered client simulator
- ConsultationTester: Test runner
- TestReporter: Report generator
"""

from .client import SimulatedClient
from .runner import ConsultationTester
from .reporter import TestReporter

__all__ = ["SimulatedClient", "ConsultationTester", "TestReporter"]
