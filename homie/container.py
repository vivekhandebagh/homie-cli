"""Docker container execution with security constraints."""

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

import docker
from docker.types import DeviceRequest

from .jobs import Job, JobResult


@dataclass
class ContainerConfig:
    """Configuration for container execution."""

    image: str = "python:3.11-slim"
    gpu_image: str = "nvidia/cuda:12.1-runtime-ubuntu22.04"
    cpu_limit: float = 2.0
    memory_limit: str = "4g"
    timeout: int = 600
    network_mode: str = "none"
    pids_limit: int = 100


class ContainerExecutor:
    """Execute jobs inside Docker containers with security constraints."""

    def __init__(self, config: Optional[ContainerConfig] = None):
        self.config = config or ContainerConfig()
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        """Lazy-load Docker client."""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            self.client.ping()
            return True
        except Exception:
            return False

    def has_gpu_support(self) -> bool:
        """Check if GPU passthrough is available."""
        try:
            self.client.containers.run(
                "nvidia/cuda:12.1-base-ubuntu22.04",
                "nvidia-smi",
                device_requests=[DeviceRequest(count=-1, capabilities=[["gpu"]])],
                remove=True,
            )
            return True
        except Exception:
            return False

    def execute(self, job: Job) -> JobResult:
        """Execute a job inside a container."""
        workspace = tempfile.mkdtemp(prefix=f"homie_{job.job_id}_")
        container = None
        start_time = time.time()

        try:
            # Write job files to workspace
            self._prepare_workspace(workspace, job)

            # Select image based on GPU requirement
            image = self.config.gpu_image if job.require_gpu else self.config.image

            # Build container run arguments
            run_kwargs = {
                "image": image,
                "command": ["python", job.filename] + job.args,
                "detach": True,
                "working_dir": "/workspace",
                "volumes": {workspace: {"bind": "/workspace", "mode": "rw"}},
                # Resource limits
                "nano_cpus": int(self.config.cpu_limit * 1e9),
                "mem_limit": self.config.memory_limit,
                "pids_limit": self.config.pids_limit,
                # Security constraints
                "network_mode": self.config.network_mode,
                "read_only": True,
                "user": "1000:1000",
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                # Temporary writable areas
                "tmpfs": {"/tmp": "size=100M,mode=1777"},
                # Environment
                "environment": {
                    "HOMIE_JOB_ID": job.job_id,
                    "PYTHONUNBUFFERED": "1",
                },
            }

            # Add GPU support if requested
            if job.require_gpu:
                run_kwargs["device_requests"] = [
                    DeviceRequest(count=-1, capabilities=[["gpu"]])
                ]

            # Run container
            container = self.client.containers.run(**run_kwargs)

            # Wait for completion
            try:
                result = container.wait(timeout=self.config.timeout)
                exit_code = result["StatusCode"]
                timed_out = False
            except Exception:
                container.kill()
                exit_code = -1
                timed_out = True

            # Collect output
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            # Collect output files
            output_files = self._collect_outputs(workspace, job)

            runtime = time.time() - start_time

            return JobResult(
                job_id=job.job_id,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                output_files=output_files,
                runtime_seconds=runtime,
                error="Execution timed out" if timed_out else None,
            )

        except docker.errors.ContainerError as e:
            return JobResult(
                job_id=job.job_id,
                exit_code=e.exit_status,
                stdout="",
                stderr=str(e),
                runtime_seconds=time.time() - start_time,
                error=str(e),
            )
        except docker.errors.ImageNotFound as e:
            return JobResult(
                job_id=job.job_id,
                exit_code=-1,
                stdout="",
                stderr="",
                runtime_seconds=0,
                error=f"Docker image not found: {e}",
            )
        except Exception as e:
            return JobResult(
                job_id=job.job_id,
                exit_code=-1,
                stdout="",
                stderr="",
                runtime_seconds=time.time() - start_time,
                error=str(e),
            )
        finally:
            # Cleanup
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            shutil.rmtree(workspace, ignore_errors=True)

    def _prepare_workspace(self, workspace: str, job: Job) -> None:
        """Write job files to workspace directory."""
        # Write main script
        script_path = os.path.join(workspace, job.filename)
        with open(script_path, "wb") as f:
            f.write(job.code)

        # Write additional files
        for filename, content in job.files.items():
            file_path = os.path.join(workspace, filename)
            os.makedirs(os.path.dirname(file_path) if "/" in filename else workspace, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(content)

    def _collect_outputs(self, workspace: str, job: Job) -> dict[str, bytes]:
        """Collect output files from workspace."""
        outputs = {}
        input_files = {job.filename} | set(job.files.keys())

        for root, _, files in os.walk(workspace):
            for filename in files:
                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, workspace)

                # Skip input files, only collect new outputs
                if relpath not in input_files:
                    try:
                        with open(filepath, "rb") as f:
                            outputs[relpath] = f.read()
                    except Exception:
                        pass

        return outputs
