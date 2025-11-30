"""TCP client for submitting jobs to peers."""

import socket
from typing import Optional

from .config import HomieConfig
from .discovery import Peer
from .jobs import Job, JobResult, deserialize_result, serialize_job


class Client:
    """Client for sending jobs to peer workers."""

    def __init__(self, config: HomieConfig):
        self.config = config

    def run_job(self, peer: Peer, job: Job, timeout: int = 600) -> JobResult:
        """
        Send a job to a peer and wait for the result.

        Args:
            peer: The peer to run the job on
            job: The job to execute
            timeout: Maximum time to wait for result (seconds)

        Returns:
            JobResult with execution output
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            # Connect to peer
            sock.connect((peer.ip, peer.port))

            # Serialize and send job
            job_data = serialize_job(job, self.config.group_secret).encode()
            sock.sendall(len(job_data).to_bytes(4, "big"))
            sock.sendall(job_data)

            # Receive result (length-prefixed)
            length_bytes = self._recv_exactly(sock, 4)
            if not length_bytes:
                return JobResult(
                    job_id=job.job_id,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    error="Connection closed by peer",
                )

            length = int.from_bytes(length_bytes, "big")
            result_data = self._recv_exactly(sock, length)

            if not result_data:
                return JobResult(
                    job_id=job.job_id,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    error="Failed to receive result from peer",
                )

            return deserialize_result(result_data.decode())

        except socket.timeout:
            return JobResult(
                job_id=job.job_id,
                exit_code=-1,
                stdout="",
                stderr="",
                error="Connection timed out",
            )
        except ConnectionRefusedError:
            return JobResult(
                job_id=job.job_id,
                exit_code=-1,
                stdout="",
                stderr="",
                error=f"Connection refused by {peer.name} ({peer.ip}:{peer.port})",
            )
        except Exception as e:
            return JobResult(
                job_id=job.job_id,
                exit_code=-1,
                stdout="",
                stderr="",
                error=str(e),
            )
        finally:
            sock.close()

    def _recv_exactly(self, sock: socket.socket, n: int) -> Optional[bytes]:
        """Receive exactly n bytes from socket."""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data
