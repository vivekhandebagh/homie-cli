"""
Mesh relay service for Homie compute.

This service runs on peers with public IPs to help coordinate onboarding
of new members when direct connection is not possible.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from .mesh import MeshManager


class RelayRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for relay service."""

    def log_message(self, format, *args):
        """Suppress default HTTP logging (too verbose)."""
        pass

    def do_GET(self):
        """Handle GET requests (lookup and health check)."""
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._handle_health()
        elif parsed.path == "/lookup":
            self._handle_lookup(parsed)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests (register and bundle proxy)."""
        parsed = urlparse(self.path)

        if parsed.path == "/register":
            self._handle_register()
        elif parsed.path == "/bundle/proxy":
            self._handle_bundle_proxy()
        else:
            self.send_error(404, "Not Found")

    def _handle_health(self):
        """Health check endpoint."""
        service: MeshRelayService = self.server.relay_service

        response = {
            "status": "healthy",
            "active_invites": len(service._invites),
            "uptime": time.time() - service._start_time
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_register(self):
        """Register an invite token."""
        service: MeshRelayService = self.server.relay_service

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Validate required fields
        if not all(k in data for k in ['token', 'inviter_mesh_ip', 'inviter_pubkey']):
            self.send_error(400, "Missing required fields")
            return

        token = data['token']
        inviter_mesh_ip = data['inviter_mesh_ip']
        inviter_pubkey = data['inviter_pubkey']

        # Store invite
        service.register_invite(token, inviter_mesh_ip, inviter_pubkey)

        response = {
            "status": "registered",
            "expires_in": service.INVITE_EXPIRY
        }

        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_lookup(self, parsed):
        """Look up an invite token."""
        service: MeshRelayService = self.server.relay_service

        # Parse query parameters
        query = parse_qs(parsed.query)
        token = query.get('token', [None])[0]

        if not token:
            self.send_error(400, "Missing token parameter")
            return

        # Look up invite
        invite_info = service.lookup_invite(token)

        if not invite_info:
            self.send_error(404, "Invite not found or expired")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(invite_info).encode())

    def _handle_bundle_proxy(self):
        """Proxy a bundle request from joiner to inviter."""
        service: MeshRelayService = self.server.relay_service

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Validate required fields
        if not all(k in data for k in ['auth_token', 'joiner_pubkey']):
            self.send_error(400, "Missing required fields")
            return

        auth_token = data['auth_token']
        joiner_pubkey = data['joiner_pubkey']

        # Look up inviter from stored invite
        invite_info = service.lookup_invite_for_proxy(auth_token)

        if not invite_info:
            self.send_error(404, "Invite not found or expired")
            return

        inviter_mesh_ip = invite_info['inviter_mesh_ip']

        # Proxy request to inviter's bundle service
        bundle_data = service.proxy_bundle_request(inviter_mesh_ip, auth_token, joiner_pubkey)

        if bundle_data:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(bundle_data).encode())
        else:
            self.send_error(502, "Failed to fetch bundle from inviter")


class MeshRelayService:
    """
    Relay service that runs on peers with public IPs.

    This service helps coordinate initial handshakes between peers
    when direct connection is not possible due to NAT.
    """

    INVITE_EXPIRY = 3600  # 1 hour in seconds
    RELAY_PORT = 8080

    def __init__(self, mesh_manager: 'MeshManager'):
        self.mesh_manager = mesh_manager
        self._invites = {}  # token -> invite_info
        self._lock = threading.Lock()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._start_time = time.time()
        self._cleanup_thread: Optional[threading.Thread] = None

    def can_relay(self) -> bool:
        """
        Check if this peer can act as a relay.

        Returns True if we have a reliable public endpoint.
        """
        from . import stun

        endpoint = stun.detect_public_endpoint()
        if not endpoint:
            return False

        # Only relay if we have good connectivity (reliability >= 80)
        return endpoint.reliability >= 80

    def start(self):
        """Start the relay service in a background thread."""
        if not self.can_relay():
            return

        if self._server is not None:
            return  # Already running

        # Get mesh IP to bind to
        mesh_ip = self.mesh_manager.network.my_mesh_ip

        # Create HTTP server
        self._server = HTTPServer((mesh_ip, self.RELAY_PORT), RelayRequestHandler)
        self._server.relay_service = self  # Pass reference to handlers

        # Start server thread
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

        print(f"[Relay] Service started on {mesh_ip}:{self.RELAY_PORT}")

    def stop(self):
        """Stop the relay service."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
            self._cleanup_thread = None
            print("[Relay] Service stopped")

    def register_invite(self, token: str, inviter_mesh_ip: str, inviter_pubkey: str):
        """
        Register an invite token.

        Args:
            token: Unique auth token from invite code
            inviter_mesh_ip: Mesh IP of the peer creating the invite
            inviter_pubkey: Public key of the inviter
        """
        with self._lock:
            self._invites[token] = {
                "inviter_mesh_ip": inviter_mesh_ip,
                "inviter_pubkey": inviter_pubkey,
                "created_at": time.time(),
                "expires_at": time.time() + self.INVITE_EXPIRY
            }

        print(f"[Relay] Registered invite: {token[:8]}... → {inviter_mesh_ip}")

    def lookup_invite(self, token: str) -> Optional[dict]:
        """
        Look up an invite token.

        Returns invite info if found and not expired, None otherwise.
        Deletes the invite after successful lookup (one-time use).
        """
        with self._lock:
            invite = self._invites.get(token)

            if not invite:
                print(f"[Relay] Lookup failed: {token[:8]}... (not found)")
                return None

            # Check if expired
            if time.time() > invite['expires_at']:
                del self._invites[token]
                print(f"[Relay] Lookup failed: {token[:8]}... (expired)")
                return None

            # Delete after first lookup (one-time use)
            del self._invites[token]

            print(f"[Relay] Lookup success: {token[:8]}... → {invite['inviter_mesh_ip']}")

            return {
                "inviter_mesh_ip": invite["inviter_mesh_ip"],
                "inviter_pubkey": invite["inviter_pubkey"]
            }

    def lookup_invite_for_proxy(self, token: str) -> Optional[dict]:
        """
        Look up an invite token for bundle proxy without deleting it.

        Used by bundle proxy endpoint - doesn't delete the token since
        we need to forward it to the inviter's bundle service.

        Returns invite info if found and not expired, None otherwise.
        """
        with self._lock:
            invite = self._invites.get(token)

            if not invite:
                print(f"[Relay] Proxy lookup failed: {token[:8]}... (not found)")
                return None

            # Check if expired
            if time.time() > invite['expires_at']:
                del self._invites[token]
                print(f"[Relay] Proxy lookup failed: {token[:8]}... (expired)")
                return None

            print(f"[Relay] Proxy lookup success: {token[:8]}... → {invite['inviter_mesh_ip']}")

            return {
                "inviter_mesh_ip": invite["inviter_mesh_ip"],
                "inviter_pubkey": invite["inviter_pubkey"]
            }

    def proxy_bundle_request(self, inviter_mesh_ip: str, auth_token: str,
                             joiner_pubkey: str) -> Optional[dict]:
        """
        Proxy a bundle request to the inviter's Worker service.

        Uses Worker protocol (TCP port 5556) with message type 'B'.

        Args:
            inviter_mesh_ip: Mesh IP of the inviter
            auth_token: Auth token from invite
            joiner_pubkey: Public key of the joiner

        Returns:
            Bundle data as dict if successful, None otherwise
        """
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)

        try:
            print(f"[Relay] Proxying bundle request to {inviter_mesh_ip}")

            # Connect to inviter's worker
            sock.connect((inviter_mesh_ip, 5556))

            # Send message type 'B' (Bundle request)
            sock.sendall(b'B')

            # Prepare payload
            payload = json.dumps({
                "auth_token": auth_token,
                "joiner_pubkey": joiner_pubkey
            }).encode()

            # Send length-prefixed payload
            sock.sendall(len(payload).to_bytes(4, "big"))
            sock.sendall(payload)

            # Receive response (1 byte: '1' = success, '0' = failure)
            status = sock.recv(1)
            if status != b'1':
                print(f"[Relay] Proxy failed: inviter rejected auth")
                return None

            # Receive bundle (length-prefixed JSON)
            length_bytes = self._recv_exactly(sock, 4)
            if not length_bytes:
                return None

            length = int.from_bytes(length_bytes, "big")
            bundle_data = self._recv_exactly(sock, length)
            if not bundle_data:
                return None

            print(f"[Relay] Successfully proxied bundle from {inviter_mesh_ip}")
            return json.loads(bundle_data.decode())

        except Exception as e:
            print(f"[Relay] Failed to proxy bundle request: {e}")
            return None
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

    def _cleanup_loop(self):
        """Background thread that periodically removes expired invites."""
        while self._server is not None:
            time.sleep(300)  # Every 5 minutes

            with self._lock:
                now = time.time()
                expired = [
                    token for token, invite in self._invites.items()
                    if now > invite['expires_at']
                ]

                for token in expired:
                    del self._invites[token]

                if expired:
                    print(f"[Relay] Cleaned up {len(expired)} expired invites")

    def is_running(self) -> bool:
        """Check if relay service is currently running."""
        return self._server is not None
