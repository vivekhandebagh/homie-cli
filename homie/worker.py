"""TCP worker daemon for receiving and executing jobs."""

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import HomieConfig
from .container import ContainerConfig, ContainerExecutor
from .jobs import Job, JobResult, deserialize_job, serialize_result


@dataclass
class RunningJob:
    """A currently running job."""

    job: Job
    start_time: float = field(default_factory=time.time)
    thread: Optional[threading.Thread] = None


class Worker:
    """TCP server that receives and executes jobs from peers."""

    def __init__(
        self,
        config: HomieConfig,
        on_job_started: Optional[Callable[[Job], None]] = None,
        on_job_completed: Optional[Callable[[JobResult], None]] = None,
        on_status_changed: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.on_job_started = on_job_started
        self.on_job_completed = on_job_completed
        self.on_status_changed = on_status_changed

        self._executor = ContainerExecutor(
            ContainerConfig(
                image=config.container_image,
                cpu_limit=config.container_cpu_limit,
                memory_limit=config.container_memory_limit,
                timeout=config.container_timeout,
                network_mode=config.container_network,
            )
        )

        self._running_jobs: dict[str, RunningJob] = {}
        self._lock = threading.Lock()
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the worker server."""
        if self._running:
            return

        self._running = True

        # Create TCP server socket
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(("", self.config.worker_port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)

        # Start server thread
        self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self._server_thread.start()

    def stop(self) -> None:
        """Stop the worker server."""
        self._running = False
        if self._server_socket:
            self._server_socket.close()

    def is_docker_available(self) -> bool:
        """Check if Docker is available for execution."""
        return self._executor.is_available()

    def has_gpu_support(self) -> bool:
        """Check if GPU support is available."""
        return self._executor.has_gpu_support()

    def get_running_jobs(self) -> list[RunningJob]:
        """Get list of currently running jobs."""
        with self._lock:
            return list(self._running_jobs.values())

    def _server_loop(self) -> None:
        """Accept incoming connections."""
        while self._running:
            try:
                conn, addr = self._server_socket.accept()
                # Handle each connection in a new thread
                thread = threading.Thread(
                    target=self._handle_connection,
                    args=(conn, addr),
                    daemon=True,
                )
                thread.start()
            except socket.timeout:
                continue
            except Exception:
                pass

    def _handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a single client connection."""
        try:
            conn.settimeout(30.0)

            # Receive job data (length-prefixed)
            length_bytes = self._recv_exactly(conn, 4)
            if not length_bytes:
                return
            length = int.from_bytes(length_bytes, "big")

            # Sanity check on length
            if length > 100 * 1024 * 1024:  # 100MB max
                self._send_error(conn, "Job payload too large")
                return

            job_data = self._recv_exactly(conn, length)
            if not job_data:
                return

            # Deserialize and verify job
            try:
                job = deserialize_job(job_data.decode(), self.config.group_secret)
            except ValueError as e:
                self._send_error(conn, str(e))
                return

            # Execute job
            result = self._execute_job(job)

            # Send result
            result_data = serialize_result(result).encode()
            conn.sendall(len(result_data).to_bytes(4, "big"))
            conn.sendall(result_data)

        except Exception as e:
            try:
                self._send_error(conn, f"Worker error: {e}")
            except Exception:
                pass
        finally:
            conn.close()

    def _recv_exactly(self, conn: socket.socket, n: int) -> Optional[bytes]:
        """Receive exactly n bytes from socket."""
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _send_error(self, conn: socket.socket, message: str) -> None:
        """Send an error response."""
        result = JobResult(
            job_id="error",
            exit_code=-1,
            stdout="",
            stderr="",
            error=message,
        )
        result_data = serialize_result(result).encode()
        conn.sendall(len(result_data).to_bytes(4, "big"))
        conn.sendall(result_data)

    def _execute_job(self, job: Job) -> JobResult:
        """Execute a job in a container."""
        # Track running job
        running_job = RunningJob(job=job)
        with self._lock:
            self._running_jobs[job.job_id] = running_job

        # Notify status change
        if self.on_status_changed:
            self.on_status_changed("busy")
        if self.on_job_started:
            self.on_job_started(job)

        try:
            # Execute in container
            result = self._executor.execute(job)
            return result
        finally:
            # Remove from running jobs
            with self._lock:
                self._running_jobs.pop(job.job_id, None)

            # Notify completion
            if self.on_job_completed:
                self.on_job_completed(result)

            # Update status if no more jobs
            with self._lock:
                if not self._running_jobs and self.on_status_changed:
                    self.on_status_changed("idle")
