"""Docker container execution with security constraints."""

import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, Optional

import docker
from docker.types import DeviceRequest

from .jobs import Job, JobResult


@dataclass
class OutputChunk:
    """A chunk of output from a running container."""
    stream: str  # "stdout" or "stderr"
    data: str


@dataclass
class ContainerConfig:
    """Configuration for container execution."""

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
        self._running_containers: dict[str, docker.models.containers.Container] = {}
        self._container_lock = threading.Lock()

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

    def _get_command(self, job: Job) -> list:
        """Detect how to run the script based on extension."""
        ext = Path(job.filename).suffix.lower()

        commands = {
            ".py": ["python", job.filename],
            ".js": ["node", job.filename],
            ".sh": ["bash", job.filename],
            ".rb": ["ruby", job.filename],
            ".pl": ["perl", job.filename],
            ".php": ["php", job.filename],
        }

        base_cmd = commands.get(ext, ["python", job.filename])
        return base_cmd + job.args

    def _ensure_image(self, image: str) -> None:
        """Pull image if not available locally."""
        try:
            self.client.images.get(image)
        except docker.errors.ImageNotFound:
            # Image not found locally, pull it
            print(f"Pulling image {image}...")
            self.client.images.pull(image)

    def execute(self, job: Job) -> JobResult:
        """Execute a job inside a container."""
        workspace = tempfile.mkdtemp(prefix=f"homie_{job.job_id}_")
        container = None
        start_time = time.time()

        try:
            # Write job files to workspace
            self._prepare_workspace(workspace, job)

            # Use image from job (sent by mooch)
            image = job.image

            # Ensure image is available (pull if needed)
            self._ensure_image(image)

            # Build container run arguments
            run_kwargs = {
                "image": image,
                "command": self._get_command(job),
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

            # Track container for potential kill
            with self._container_lock:
                self._running_containers[job.job_id] = container

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
            # Remove from tracking
            with self._container_lock:
                self._running_containers.pop(job.job_id, None)

            # Cleanup
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            shutil.rmtree(workspace, ignore_errors=True)

    def execute_streaming(
        self,
        job: Job,
        on_output: Callable[[OutputChunk], None]
    ) -> JobResult:
        """Execute a job inside a container, streaming output via callback.

        Args:
            job: The job to execute
            on_output: Callback called with each output chunk

        Returns:
            JobResult with final execution info
        """
        workspace = tempfile.mkdtemp(prefix=f"homie_{job.job_id}_")
        container = None
        start_time = time.time()

        try:
            # Write job files to workspace
            self._prepare_workspace(workspace, job)

            # Use image from job (sent by mooch)
            image = job.image

            # Ensure image is available (pull if needed)
            self._ensure_image(image)

            # Build container run arguments
            run_kwargs = {
                "image": image,
                "command": self._get_command(job),
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

            # Track container for potential kill
            with self._container_lock:
                self._running_containers[job.job_id] = container

            # Stream logs in real-time
            timed_out = False
            stdout_full = []
            stderr_full = []

            try:
                # Use logs with stream=True to get output as it happens
                # We use a separate thread to handle timeout
                log_stream = container.logs(
                    stdout=True,
                    stderr=True,
                    stream=True,
                    follow=True
                )

                # Docker demultiplexes stdout/stderr when using stream=True with TTY=False
                # Each chunk is prefixed with 8-byte header: [stream_type(1), 0, 0, 0, size(4)]
                for chunk in log_stream:
                    # Decode the chunk
                    text = chunk.decode("utf-8", errors="replace")
                    if text:
                        # Docker SDK with stream=True gives us raw bytes
                        # When TTY is false (our case), it's mixed but we treat as stdout
                        stdout_full.append(text)
                        on_output(OutputChunk(stream="stdout", data=text))

                    # Check if container is still running
                    container.reload()
                    if container.status != "running":
                        break

            except Exception as e:
                # Timeout or other error during streaming
                if "timed out" in str(e).lower():
                    timed_out = True
                    try:
                        container.kill()
                    except Exception:
                        pass

            # Get final exit code
            try:
                container.reload()
                exit_code = container.attrs.get("State", {}).get("ExitCode", -1)
            except Exception:
                exit_code = -1

            # Collect output files
            output_files = self._collect_outputs(workspace, job)

            runtime = time.time() - start_time

            return JobResult(
                job_id=job.job_id,
                exit_code=exit_code,
                stdout="".join(stdout_full),
                stderr="".join(stderr_full),
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
            # Remove from tracking
            with self._container_lock:
                self._running_containers.pop(job.job_id, None)

            # Cleanup
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            shutil.rmtree(workspace, ignore_errors=True)

    def kill_job(self, job_id: str) -> bool:
        """Kill a running job by ID. Returns True if killed, False if not found."""
        with self._container_lock:
            container = self._running_containers.get(job_id)

        if container:
            try:
                container.kill()
                return True
            except Exception:
                return False
        return False

    def get_running_job_ids(self) -> list[str]:
        """Get list of currently running job IDs."""
        with self._container_lock:
            return list(self._running_containers.keys())

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
