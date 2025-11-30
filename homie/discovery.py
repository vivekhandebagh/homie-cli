"""UDP broadcast discovery and peer tracking."""

import hashlib
import hmac
import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import HomieConfig
from .utils import get_local_ip, get_system_stats


@dataclass
class Peer:
    """A peer on the network."""

    name: str
    ip: str
    port: int
    cpu_percent_used: float
    ram_free_gb: float
    ram_total_gb: float
    gpu_name: Optional[str]
    gpu_memory_free_gb: Optional[float]
    status: str  # "idle" or "busy"
    last_seen: float = field(default_factory=time.time)

    @property
    def is_alive(self) -> bool:
        """Check if peer is still alive (seen within timeout)."""
        return time.time() - self.last_seen < 10.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "cpu_percent_used": self.cpu_percent_used,
            "ram_free_gb": self.ram_free_gb,
            "ram_total_gb": self.ram_total_gb,
            "gpu_name": self.gpu_name,
            "gpu_memory_free_gb": self.gpu_memory_free_gb,
            "status": self.status,
        }


def sign_heartbeat(data: dict, secret: str) -> str:
    """Sign heartbeat data with group secret."""
    msg = json.dumps(data, sort_keys=True).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_heartbeat(data: dict, signature: str, secret: str) -> bool:
    """Verify heartbeat signature."""
    expected = sign_heartbeat(data, secret)
    return hmac.compare_digest(expected, signature)


class Discovery:
    """UDP broadcast discovery service with direct peer support."""

    def __init__(
        self,
        config: HomieConfig,
        on_peer_joined: Optional[Callable[[Peer], None]] = None,
        on_peer_left: Optional[Callable[[Peer], None]] = None,
    ):
        self.config = config
        self.on_peer_joined = on_peer_joined
        self.on_peer_left = on_peer_left

        self._peers: dict[str, Peer] = {}
        self._direct_peers: list[str] = []  # List of IPs to send direct heartbeats to
        self._lock = threading.Lock()
        self._running = False
        self._status = "idle"

        self._broadcast_thread: Optional[threading.Thread] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None

        self._broadcast_socket: Optional[socket.socket] = None
        self._listen_socket: Optional[socket.socket] = None

        # Load direct peers from config file
        self._load_direct_peers()

    def start(self, listen: bool = True) -> None:
        """Start the discovery service.

        Args:
            listen: If True, bind to port and listen for peers (for homie up).
                   If False, only send broadcasts and receive responses (for homie peers/run).
        """
        if self._running:
            return

        self._running = True
        self._listen_mode = listen

        # Create broadcast socket
        self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if listen:
            # Full listen mode - bind to port (for homie up)
            self._listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._listen_socket.bind(("", self.config.discovery_port))
            self._listen_socket.settimeout(1.0)
        else:
            # Client mode - use a random port to receive responses
            self._listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._listen_socket.bind(("", 0))  # Random available port
            self._listen_socket.settimeout(1.0)

        # Start threads
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)

        self._broadcast_thread.start()
        self._listen_thread.start()
        self._cleanup_thread.start()

    def stop(self) -> None:
        """Stop the discovery service."""
        self._running = False

        if self._broadcast_socket:
            self._broadcast_socket.close()
        if self._listen_socket:
            self._listen_socket.close()

    def set_status(self, status: str) -> None:
        """Set current status (idle/busy)."""
        self._status = status

    def get_peers(self) -> list[Peer]:
        """Get list of all known alive peers."""
        with self._lock:
            return [p for p in self._peers.values() if p.is_alive]

    def get_peer(self, name: str) -> Optional[Peer]:
        """Get a specific peer by name."""
        with self._lock:
            peer = self._peers.get(name)
            return peer if peer and peer.is_alive else None

    def get_best_peer(self, require_gpu: bool = False) -> Optional[Peer]:
        """Get the best available peer for running a job."""
        peers = self.get_peers()

        # Filter by status and GPU requirement
        available = [
            p for p in peers
            if p.status == "idle" and (not require_gpu or p.gpu_name)
        ]

        if not available:
            return None

        # Score peers: prefer more free RAM, less CPU usage
        def score(p: Peer) -> float:
            ram_score = p.ram_free_gb
            cpu_score = (100 - p.cpu_percent_used) / 100
            gpu_bonus = 2.0 if p.gpu_name and require_gpu else 0
            return ram_score * cpu_score + gpu_bonus

        return max(available, key=score)

    def _build_heartbeat(self) -> dict:
        """Build heartbeat message."""
        stats = get_system_stats()
        return {
            "name": self.config.name,
            "ip": get_local_ip(),
            "port": self.config.worker_port,
            "cpu_percent_used": stats.cpu_percent_used,
            "ram_free_gb": round(stats.ram_free_gb, 2),
            "ram_total_gb": round(stats.ram_total_gb, 2),
            "gpu_name": stats.gpu_name,
            "gpu_memory_free_gb": round(stats.gpu_memory_free_gb, 2) if stats.gpu_memory_free_gb else None,
            "status": self._status,
            "timestamp": time.time(),
        }

    def _load_direct_peers(self) -> None:
        """Load direct peer IPs from ~/.homie/peers file."""
        from pathlib import Path
        peers_file = Path.home() / ".homie" / "peers"
        if peers_file.exists():
            content = peers_file.read_text().strip()
            self._direct_peers = [ip.strip() for ip in content.split("\n") if ip.strip()]

    def add_direct_peer(self, ip: str) -> None:
        """Add a direct peer IP and save to file."""
        from pathlib import Path
        if ip not in self._direct_peers:
            self._direct_peers.append(ip)
            peers_file = Path.home() / ".homie" / "peers"
            peers_file.parent.mkdir(parents=True, exist_ok=True)
            peers_file.write_text("\n".join(self._direct_peers) + "\n")

    def remove_direct_peer(self, ip: str) -> None:
        """Remove a direct peer IP."""
        from pathlib import Path
        if ip in self._direct_peers:
            self._direct_peers.remove(ip)
            peers_file = Path.home() / ".homie" / "peers"
            if self._direct_peers:
                peers_file.write_text("\n".join(self._direct_peers) + "\n")
            elif peers_file.exists():
                peers_file.unlink()

    def _broadcast_loop(self) -> None:
        """Broadcast heartbeat periodically."""
        while self._running:
            try:
                heartbeat = self._build_heartbeat()
                signature = sign_heartbeat(heartbeat, self.config.group_secret)

                message = json.dumps({"heartbeat": heartbeat, "sig": signature}).encode()

                # Send broadcast (for networks that support it)
                self._broadcast_socket.sendto(
                    message,
                    ("<broadcast>", self.config.discovery_port),
                )

                # Also send directly to known peers (for networks that block broadcast)
                for peer_ip in self._direct_peers:
                    try:
                        self._broadcast_socket.sendto(
                            message,
                            (peer_ip, self.config.discovery_port),
                        )
                    except Exception:
                        pass
            except Exception:
                pass

            time.sleep(self.config.heartbeat_interval)

    def _listen_loop(self) -> None:
        """Listen for heartbeats from other peers."""
        while self._running:
            try:
                data, addr = self._listen_socket.recvfrom(4096)
                self._handle_message(data, addr)
            except socket.timeout:
                continue
            except Exception:
                pass

    def _handle_message(self, data: bytes, addr: tuple) -> None:
        """Handle incoming heartbeat message."""
        try:
            payload = json.loads(data.decode())
            heartbeat = payload.get("heartbeat", {})
            signature = payload.get("sig", "")

            # Verify signature
            if not verify_heartbeat(heartbeat, signature, self.config.group_secret):
                return  # Invalid signature, ignore

            # Ignore our own broadcasts
            if heartbeat.get("name") == self.config.name:
                return

            peer = Peer(
                name=heartbeat["name"],
                ip=heartbeat["ip"],
                port=heartbeat["port"],
                cpu_percent_used=heartbeat["cpu_percent_used"],
                ram_free_gb=heartbeat["ram_free_gb"],
                ram_total_gb=heartbeat["ram_total_gb"],
                gpu_name=heartbeat.get("gpu_name"),
                gpu_memory_free_gb=heartbeat.get("gpu_memory_free_gb"),
                status=heartbeat["status"],
                last_seen=time.time(),
            )

            with self._lock:
                is_new = peer.name not in self._peers
                self._peers[peer.name] = peer

            if is_new and self.on_peer_joined:
                self.on_peer_joined(peer)

        except Exception:
            pass

    def _cleanup_loop(self) -> None:
        """Remove dead peers periodically."""
        while self._running:
            time.sleep(self.config.peer_timeout / 2)

            with self._lock:
                dead_peers = [
                    name for name, peer in self._peers.items()
                    if not peer.is_alive
                ]
                for name in dead_peers:
                    peer = self._peers.pop(name)
                    if self.on_peer_left:
                        self.on_peer_left(peer)
