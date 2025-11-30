"""Job history tracking for Homie Compute."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


HISTORY_FILE = Path.home() / ".homie" / "job_history.jsonl"
MAX_HISTORY_ENTRIES = 1000  # Keep last 1000 jobs


@dataclass
class JobHistoryEntry:
    """A single job history entry."""

    job_id: str
    sender: str
    peer: str  # Peer who ran the job (for mooch) or peer who sent it (for plug)
    filename: str
    args: list[str]
    image: str
    require_gpu: bool
    role: str  # "mooch" (you sent it) or "plug" (you ran it)

    # Timing
    start_time: float
    end_time: Optional[float] = None
    runtime_seconds: Optional[float] = None

    # Result
    exit_code: Optional[int] = None
    success: Optional[bool] = None
    error: Optional[str] = None

    # Metadata
    output_file_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "job_id": self.job_id,
            "sender": self.sender,
            "peer": self.peer,
            "filename": self.filename,
            "args": self.args,
            "image": self.image,
            "require_gpu": self.require_gpu,
            "role": self.role,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "runtime_seconds": self.runtime_seconds,
            "exit_code": self.exit_code,
            "success": self.success,
            "error": self.error,
            "output_file_count": self.output_file_count,
        }

    @staticmethod
    def from_dict(data: dict) -> "JobHistoryEntry":
        """Create from dictionary."""
        return JobHistoryEntry(
            job_id=data["job_id"],
            sender=data["sender"],
            peer=data["peer"],
            filename=data["filename"],
            args=data["args"],
            image=data.get("image", "python:3.11-slim"),
            require_gpu=data.get("require_gpu", False),
            role=data["role"],
            start_time=data["start_time"],
            end_time=data.get("end_time"),
            runtime_seconds=data.get("runtime_seconds"),
            exit_code=data.get("exit_code"),
            success=data.get("success"),
            error=data.get("error"),
            output_file_count=data.get("output_file_count", 0),
        )


def ensure_history_file() -> None:
    """Ensure history file exists."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()


def append_job_start(
    job_id: str,
    sender: str,
    peer: str,
    filename: str,
    args: list[str],
    image: str,
    require_gpu: bool,
    role: str,
) -> None:
    """Record a job start in history."""
    ensure_history_file()

    entry = JobHistoryEntry(
        job_id=job_id,
        sender=sender,
        peer=peer,
        filename=filename,
        args=args,
        image=image,
        require_gpu=require_gpu,
        role=role,
        start_time=time.time(),
    )

    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")


def update_job_completion(
    job_id: str,
    exit_code: int,
    runtime_seconds: float,
    error: Optional[str] = None,
    output_file_count: int = 0,
) -> None:
    """Update a job entry with completion info."""
    ensure_history_file()

    # Read all entries
    entries = read_history()

    # Find and update the matching entry
    updated = False
    for entry in reversed(entries):  # Search from end (most recent)
        if entry.job_id == job_id and entry.end_time is None:
            entry.end_time = time.time()
            entry.runtime_seconds = runtime_seconds
            entry.exit_code = exit_code
            entry.success = exit_code == 0 and error is None
            entry.error = error
            entry.output_file_count = output_file_count
            updated = True
            break

    if updated:
        # Rewrite the file with updated entries
        _write_history(entries)


def read_history(
    limit: Optional[int] = None,
    role: Optional[str] = None,
    peer: Optional[str] = None,
    success_only: bool = False,
    failed_only: bool = False,
    since: Optional[float] = None,
) -> list[JobHistoryEntry]:
    """Read job history with optional filters.

    Args:
        limit: Maximum number of entries to return
        role: Filter by role ("mooch" or "plug")
        peer: Filter by peer name
        success_only: Only return successful jobs
        failed_only: Only return failed jobs
        since: Only return jobs after this timestamp

    Returns:
        List of job history entries, newest first
    """
    ensure_history_file()

    entries = []
    try:
        with open(HISTORY_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = JobHistoryEntry.from_dict(data)

                    # Apply filters
                    if role and entry.role != role:
                        continue
                    if peer and entry.peer != peer:
                        continue
                    if success_only and not entry.success:
                        continue
                    if failed_only and entry.success:
                        continue
                    if since and entry.start_time < since:
                        continue

                    entries.append(entry)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # Skip malformed entries
                    continue
    except FileNotFoundError:
        return []

    # Sort by start time, newest first
    entries.sort(key=lambda e: e.start_time, reverse=True)

    # Apply limit
    if limit:
        entries = entries[:limit]

    return entries


def get_history_stats() -> dict:
    """Get summary statistics about job history.

    Returns:
        Dictionary with stats like total jobs, success rate, etc.
    """
    entries = read_history()

    if not entries:
        return {
            "total_jobs": 0,
            "completed_jobs": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "running_jobs": 0,
            "success_rate": 0.0,
            "avg_runtime": 0.0,
            "total_runtime": 0.0,
        }

    completed = [e for e in entries if e.end_time is not None]
    successful = [e for e in completed if e.success]
    failed = [e for e in completed if not e.success]
    running = [e for e in entries if e.end_time is None]

    total_runtime = sum(e.runtime_seconds for e in completed if e.runtime_seconds)
    avg_runtime = total_runtime / len(completed) if completed else 0.0
    success_rate = (len(successful) / len(completed) * 100) if completed else 0.0

    return {
        "total_jobs": len(entries),
        "completed_jobs": len(completed),
        "successful_jobs": len(successful),
        "failed_jobs": len(failed),
        "running_jobs": len(running),
        "success_rate": success_rate,
        "avg_runtime": avg_runtime,
        "total_runtime": total_runtime,
    }


def _write_history(entries: list[JobHistoryEntry]) -> None:
    """Write all history entries to file (overwrites existing)."""
    # Limit to max entries to prevent file from growing too large
    if len(entries) > MAX_HISTORY_ENTRIES:
        entries = entries[-MAX_HISTORY_ENTRIES:]

    with open(HISTORY_FILE, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_dict()) + "\n")


def clear_history() -> int:
    """Clear all job history.

    Returns:
        Number of entries cleared
    """
    count = len(read_history())
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    return count
