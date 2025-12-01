"""TCP worker daemon for receiving and executing jobs."""

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import HomieConfig
from .container import ContainerConfig, ContainerExecutor, OutputChunk
from .history import append_job_start, update_job_completion
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

            # Receive message type (1 byte)
            msg_type = self._recv_exactly(conn, 1)
            if not msg_type:
                return

            if msg_type == b'J':
                # Job submission
                self._handle_job_submission(conn)
            elif msg_type == b'K':
                # Kill request
                self._handle_kill_request(conn)
            elif msg_type == b'L':
                # List jobs request
                self._handle_list_request(conn)
            else:
                self._send_error(conn, f"Unknown message type: {msg_type}")

        except Exception as e:
            try:
                self._send_error(conn, f"Worker error: {e}")
            except Exception:
                pass
        finally:
            conn.close()

    def _handle_job_submission(self, conn: socket.socket) -> None:
        """Handle a job submission request with streaming output."""
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

        # Execute job with streaming output
        result = self._execute_job_streaming(job, conn)

        # Send final result (message type 'R')
        conn.sendall(b'R')
        result_data = serialize_result(result).encode()
        conn.sendall(len(result_data).to_bytes(4, "big"))
        conn.sendall(result_data)

    def _handle_kill_request(self, conn: socket.socket) -> None:
        """Handle a kill request."""
        # Receive kill payload (length-prefixed JSON)
        length_bytes = self._recv_exactly(conn, 4)
        if not length_bytes:
            return
        length = int.from_bytes(length_bytes, "big")

        payload_data = self._recv_exactly(conn, length)
        if not payload_data:
            return

        try:
            payload = json.loads(payload_data.decode())
            job_id = payload["job_id"]
            requester = payload["requester"]  # Who's requesting the kill
            auth_hmac = payload["auth"]["hmac"]
            timestamp = payload["auth"]["timestamp"]

            # Verify auth (simple HMAC check)
            from .jobs import verify_auth_hmac
            if not verify_auth_hmac(job_id, timestamp, auth_hmac, self.config.group_secret):
                conn.sendall(b'0')  # Auth failed
                return

            # Check timestamp freshness
            if abs(time.time() - timestamp) > 300:
                conn.sendall(b'0')  # Too old
                return

            # Check if requester is authorized to kill this job
            # Only the original sender or the plug (local) can kill a job
            with self._lock:
                running_job = self._running_jobs.get(job_id)

            if not running_job:
                conn.sendall(b'0')  # Job not found
                return

            original_sender = running_job.job.sender
            if requester != original_sender:
                conn.sendall(b'0')  # Not authorized
                return

            # Try to kill the job
            success = self._executor.kill_job(job_id)
            conn.sendall(b'1' if success else b'0')

        except Exception:
            conn.sendall(b'0')

    def _handle_list_request(self, conn: socket.socket) -> None:
        """Handle a list jobs request."""
        # Receive auth payload
        length_bytes = self._recv_exactly(conn, 4)
        if not length_bytes:
            return
        length = int.from_bytes(length_bytes, "big")

        payload_data = self._recv_exactly(conn, length)
        if not payload_data:
            return

        try:
            payload = json.loads(payload_data.decode())
            auth_hmac = payload["auth"]["hmac"]
            timestamp = payload["auth"]["timestamp"]

            # Verify auth
            from .jobs import verify_auth_hmac
            if not verify_auth_hmac("list", timestamp, auth_hmac, self.config.group_secret):
                conn.sendall(b'0')
                return

            # Get running jobs
            jobs_info = []
            with self._lock:
                for job_id, running_job in self._running_jobs.items():
                    jobs_info.append({
                        "job_id": job_id,
                        "sender": running_job.job.sender,
                        "filename": running_job.job.filename,
                        "start_time": running_job.start_time,
                    })

            # Send response
            response = json.dumps({"jobs": jobs_info}).encode()
            conn.sendall(b'1')  # Success
            conn.sendall(len(response).to_bytes(4, "big"))
            conn.sendall(response)

        except Exception:
            conn.sendall(b'0')

    def kill_job(self, job_id: str) -> bool:
        """Kill a job running on this worker (local call)."""
        return self._executor.kill_job(job_id)

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

    def _execute_job_streaming(self, job: Job, conn: socket.socket) -> JobResult:
        """Execute a job in a container with streaming output to connection."""
        # Track running job
        running_job = RunningJob(job=job)
        with self._lock:
            self._running_jobs[job.job_id] = running_job

        # Log job start to history (plug perspective)
        append_job_start(
            job_id=job.job_id,
            sender=job.sender,
            peer=job.sender,  # From plug's perspective, peer is the sender
            filename=job.filename,
            args=job.args,
            image=job.image,
            require_gpu=job.require_gpu,
            role="plug",
        )

        # Notify status change
        if self.on_status_changed:
            self.on_status_changed("busy")
        if self.on_job_started:
            self.on_job_started(job)

        def send_output_chunk(chunk: OutputChunk):
            """Send an output chunk over the connection."""
            try:
                # Message type: 'O' for stdout, 'E' for stderr
                msg_type = b'O' if chunk.stream == "stdout" else b'E'
                data = chunk.data.encode("utf-8")
                conn.sendall(msg_type)
                conn.sendall(len(data).to_bytes(4, "big"))
                conn.sendall(data)
            except Exception:
                pass  # Connection may be closed

        result = None
        try:
            # Execute in container with streaming
            result = self._executor.execute_streaming(job, send_output_chunk)

            # Log job completion to history
            update_job_completion(
                job_id=job.job_id,
                exit_code=result.exit_code,
                runtime_seconds=result.runtime_seconds,
                error=result.error,
                output_file_count=len(result.output_files),
            )

            return result
        finally:
            # Remove from running jobs
            with self._lock:
                self._running_jobs.pop(job.job_id, None)

            # Notify completion
            if self.on_job_completed and result:
                self.on_job_completed(result)

            # Update status if no more jobs
            with self._lock:
                if not self._running_jobs and self.on_status_changed:
                    self.on_status_changed("idle")
