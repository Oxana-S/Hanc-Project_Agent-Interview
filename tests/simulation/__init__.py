"""
Simulation framework for testing ConsultantInterviewer.

Reusable components:
- SimulatedClient: AI-powered client simulator
- ConsultationTester: Test runner
- TestReporter: Report generator
"""

from tests.simulation.client import SimulatedClient
from tests.simulation.runner import ConsultationTester
from tests.simulation.reporter import TestReporter

__all__ = ["SimulatedClient", "ConsultationTester", "TestReporter"]
