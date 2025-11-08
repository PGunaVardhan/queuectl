"""
Data models for jobs and configuration.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class JobState(str, Enum):
    """Job lifecycle states."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"  # DLQ state


@dataclass
class Job:
    """
    Represents a job in the queue.
    
    We use a dataclass because they're clean and Python 3.10+ supports them well.
    """
    id: str
    command: str
    state: JobState = JobState.PENDING
    attempts: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    output: Optional[str] = None
    run_at: Optional[datetime] = None  # For scheduled jobs
    timeout: Optional[int] = None  # Timeout in seconds
    
    def to_dict(self):
        """Convert to dict for JSON serialization."""
        return {
            "id": self.id,
            "command": self.command,
            "state": self.state.value,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error,
            "output": self.output,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "timeout": self.timeout,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create Job from dict."""
        return cls(
            id=data["id"],
            command=data["command"],
            state=JobState(data["state"]),
            attempts=data["attempts"],
            max_retries=data["max_retries"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            error=data.get("error"),
            output=data.get("output"),
            run_at=datetime.fromisoformat(data["run_at"]) if data.get("run_at") else None,
            timeout=data.get("timeout"),
        )