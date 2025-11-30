"""TCP client for submitting jobs to peers."""

import json
import socket
import time
from typing import Optional

from .config import HomieConfig
from .discovery import Peer
from .jobs import Job, JobResult, compute_auth_hmac, deserialize_result, serialize_job


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

            # Send message type prefix
            sock.sendall(b'J')

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

    def kill_job(self, peer: Peer, job_id: str, timeout: int = 10) -> bool:
        """
        Send a kill request to a peer to stop a running job.

        Args:
            peer: The peer running the job
            job_id: The ID of the job to kill
            timeout: Connection timeout in seconds

        Returns:
            True if job was killed, False otherwise
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((peer.ip, peer.port))

            # Send message type prefix
            sock.sendall(b'K')

            # Build kill payload with auth
            timestamp = time.time()
            auth_hmac = compute_auth_hmac(job_id, timestamp, self.config.group_secret)
            payload = json.dumps({
                "job_id": job_id,
                "requester": self.config.name,  # Only sender can kill their own jobs
                "auth": {
                    "hmac": auth_hmac,
                    "timestamp": timestamp,
                }
            }).encode()

            # Send length-prefixed payload
            sock.sendall(len(payload).to_bytes(4, "big"))
            sock.sendall(payload)

            # Receive result (1 byte: '1' = success, '0' = failure)
            result = sock.recv(1)
            return result == b'1'

        except Exception:
            return False
        finally:
            sock.close()

    def list_jobs(self, peer: Peer, timeout: int = 10) -> Optional[list[dict]]:
        """
        List jobs running on a peer.

        Args:
            peer: The peer to query
            timeout: Connection timeout in seconds

        Returns:
            List of job info dicts, or None on error
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((peer.ip, peer.port))

            # Send message type prefix
            sock.sendall(b'L')

            # Build auth payload
            timestamp = time.time()
            auth_hmac = compute_auth_hmac("list", timestamp, self.config.group_secret)
            payload = json.dumps({
                "auth": {
                    "hmac": auth_hmac,
                    "timestamp": timestamp,
                }
            }).encode()

            # Send length-prefixed payload
            sock.sendall(len(payload).to_bytes(4, "big"))
            sock.sendall(payload)

            # Receive result (1 byte status, then length-prefixed JSON if success)
            status = sock.recv(1)
            if status != b'1':
                return None

            length_bytes = self._recv_exactly(sock, 4)
            if not length_bytes:
                return None

            length = int.from_bytes(length_bytes, "big")
            response_data = self._recv_exactly(sock, length)
            if not response_data:
                return None

            response = json.loads(response_data.decode())
            return response.get("jobs", [])

        except Exception:
            return None
        finally:
            sock.close()
