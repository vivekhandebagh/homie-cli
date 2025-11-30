"""Job serialization and authentication."""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Job:
    """A compute job to be executed on a peer."""

    job_id: str
    sender: str
    filename: str
    code: bytes
    args: list[str] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)
    require_gpu: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class JobResult:
    """Result of job execution."""

    job_id: str
    exit_code: int
    stdout: str
    stderr: str
    output_files: dict[str, bytes] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    error: Optional[str] = None


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return uuid.uuid4().hex[:8]


def create_job(
    sender: str,
    script_path: str,
    args: list[str] = None,
    extra_files: list[str] = None,
    require_gpu: bool = False,
) -> Job:
    """Create a job from a script file."""
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    with open(path, "rb") as f:
        code = f.read()

    files = {}
    for file_path in extra_files or []:
        fp = Path(file_path)
        if fp.exists():
            with open(fp, "rb") as f:
                files[fp.name] = f.read()

    return Job(
        job_id=generate_job_id(),
        sender=sender,
        filename=path.name,
        code=code,
        args=args or [],
        files=files,
        require_gpu=require_gpu,
    )


def compute_auth_hmac(job_id: str, timestamp: float, group_secret: str) -> str:
    """Compute HMAC for job authentication."""
    msg = f"{job_id}:{timestamp}".encode()
    return hmac.new(group_secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_auth_hmac(
    job_id: str, timestamp: float, provided_hmac: str, group_secret: str
) -> bool:
    """Verify job authentication HMAC."""
    expected = compute_auth_hmac(job_id, timestamp, group_secret)
    return hmac.compare_digest(expected, provided_hmac)


def serialize_job(job: Job, group_secret: str) -> str:
    """Serialize a job to JSON with authentication."""
    auth_hmac = compute_auth_hmac(job.job_id, job.timestamp, group_secret)

    payload = {
        "job": {
            "job_id": job.job_id,
            "sender": job.sender,
            "filename": job.filename,
            "code": base64.b64encode(job.code).decode(),
            "args": job.args,
            "files": {k: base64.b64encode(v).decode() for k, v in job.files.items()},
            "require_gpu": job.require_gpu,
            "timestamp": job.timestamp,
        },
        "auth": {
            "hmac": auth_hmac,
        },
    }
    return json.dumps(payload)


def deserialize_job(data: str, group_secret: str) -> Job:
    """Deserialize a job from JSON and verify authentication."""
    payload = json.loads(data)

    job_data = payload["job"]
    auth_data = payload["auth"]

    # Verify authentication
    if not verify_auth_hmac(
        job_data["job_id"],
        job_data["timestamp"],
        auth_data["hmac"],
        group_secret,
    ):
        raise ValueError("Job authentication failed - invalid HMAC")

    # Check timestamp freshness (within 5 minutes)
    if abs(time.time() - job_data["timestamp"]) > 300:
        raise ValueError("Job authentication failed - timestamp too old")

    return Job(
        job_id=job_data["job_id"],
        sender=job_data["sender"],
        filename=job_data["filename"],
        code=base64.b64decode(job_data["code"]),
        args=job_data["args"],
        files={k: base64.b64decode(v) for k, v in job_data["files"].items()},
        require_gpu=job_data.get("require_gpu", False),
        timestamp=job_data["timestamp"],
    )


def serialize_result(result: JobResult) -> str:
    """Serialize a job result to JSON."""
    return json.dumps(
        {
            "job_id": result.job_id,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output_files": {
                k: base64.b64encode(v).decode() for k, v in result.output_files.items()
            },
            "runtime_seconds": result.runtime_seconds,
            "error": result.error,
        }
    )


def deserialize_result(data: str) -> JobResult:
    """Deserialize a job result from JSON."""
    payload = json.loads(data)
    return JobResult(
        job_id=payload["job_id"],
        exit_code=payload["exit_code"],
        stdout=payload["stdout"],
        stderr=payload["stderr"],
        output_files={
            k: base64.b64decode(v) for k, v in payload.get("output_files", {}).items()
        },
        runtime_seconds=payload.get("runtime_seconds", 0.0),
        error=payload.get("error"),
    )
