"""
Pydantic models for consultation session management.

ConsultationSession stores the full state of a voice consultation,
including dialogue history, anketa data, and session metadata.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Valid session statuses
VALID_STATUSES = {"active", "paused", "reviewing", "confirmed", "declined"}


class ConsultationSession(BaseModel):
    """
    Represents a single voice consultation session.

    Each session is created when a client connects to a LiveKit room
    and tracks the entire lifecycle of the consultation.
    """

    session_id: str = Field(..., description="Short UUID (8 chars)")
    room_name: str = Field(default="", description="LiveKit room name")
    unique_link: str = Field(..., description="Full UUID link for client to return later")
    status: str = Field(default="active", description="Session status: active, paused, reviewing, confirmed, declined")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    # Dialogue
    dialogue_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Full dialogue history with role, content, timestamp, phase"
    )

    # Anketa data (JSON-serializable dict from FinalAnketa.model_dump())
    anketa_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Anketa data as dict (from FinalAnketa.model_dump())"
    )
    anketa_md: Optional[str] = Field(
        default=None,
        description="Anketa rendered as Markdown"
    )

    # Metadata
    company_name: Optional[str] = Field(default=None, description="Company name from consultation")
    contact_name: Optional[str] = Field(default=None, description="Contact person name")
    duration_seconds: float = Field(default=0.0, description="Consultation duration in seconds")
    output_dir: Optional[str] = Field(default=None, description="Path to output directory with saved files")
