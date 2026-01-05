"""
WireGuard mesh network management for Homie Compute.

This module implements a decentralized P2P mesh network using WireGuard.
Key features:
- No central server - every peer is equal
- Any peer can invite new members
- Short invite codes (~50 chars) shared out-of-band
- Full network bundle transferred encrypted over WireGuard
"""

import base64
import json
import os
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import HOMIE_DIR


# Mesh network directories
NETWORK_DIR = HOMIE_DIR / "network"
PEERS_DIR = NETWORK_DIR / "peers"
WIREGUARD_DIR = HOMIE_DIR / "wireguard"

# WireGuard mesh settings
MESH_SUBNET = "10.100.0.0/16"  # Private subnet for mesh
WIREGUARD_PORT = 51820
INTERFACE_NAME = "homie0"


@dataclass
class Identity:
    """Local WireGuard identity (keypair)."""

    private_key: str  # WireGuard private key (base64)
    public_key: str   # WireGuard public key (base64)

    @classmethod
    def generate(cls) -> "Identity":
        """Generate a new WireGuard keypair.

        Tries to use the 'wg' command first, falls back to pure Python.
        """
        # Try using wg command first (most compatible with WireGuard)
        try:
            private_key = subprocess.check_output(
                ["wg", "genkey"],
                stderr=subprocess.DEVNULL
            ).decode().strip()

            public_key = subprocess.check_output(
                ["wg", "pubkey"],
                input=private_key.encode(),
                stderr=subprocess.DEVNULL
            ).decode().strip()

            return cls(private_key=private_key, public_key=public_key)
        except FileNotFoundError:
            # Fall back to pure Python implementation
            return cls._generate_python()

    @classmethod
    def _generate_python(cls) -> "Identity":
        """Generate keypair using pure Python (Curve25519)."""
        try:
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
            from cryptography.hazmat.primitives import serialization

            # Generate private key
            private_key_obj = X25519PrivateKey.generate()

            # Get raw private key bytes (32 bytes)
            private_key_bytes = private_key_obj.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )

            # Get public key bytes
            public_key_bytes = private_key_obj.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )

            # Encode as base64 (WireGuard format)
            private_key = base64.b64encode(private_key_bytes).decode()
            public_key = base64.b64encode(public_key_bytes).decode()

            return cls(private_key=private_key, public_key=public_key)
        except ImportError:
            raise RuntimeError(
                "WireGuard tools not found and 'cryptography' package not installed.\n"
                "Install one of:\n"
                "  pip install cryptography\n"
                "  brew install wireguard-tools (macOS)\n"
                "  sudo apt install wireguard-tools (Linux)"
            )

    def to_dict(self) -> dict:
        return {
            "private_key": self.private_key,
            "public_key": self.public_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Identity":
        return cls(
            private_key=data["private_key"],
            public_key=data["public_key"],
        )


@dataclass
class Peer:
    """A peer in the mesh network."""

    name: str
    public_key: str           # WireGuard public key
    mesh_ip: str              # IP within the mesh (e.g., 10.100.0.2)
    endpoints: list[str] = field(default_factory=list)  # External endpoints (ip:port)
    invited_by: Optional[str] = None  # Name of peer who invited this one

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "public_key": self.public_key,
            "mesh_ip": self.mesh_ip,
            "endpoints": self.endpoints,
            "invited_by": self.invited_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Peer":
        return cls(
            name=data["name"],
            public_key=data["public_key"],
            mesh_ip=data["mesh_ip"],
            endpoints=data.get("endpoints", []),
            invited_by=data.get("invited_by"),
        )


@dataclass
class Network:
    """Mesh network metadata."""

    name: str
    group_secret: str         # Shared secret for Homie job auth
    my_mesh_ip: str           # This node's IP in the mesh
    next_ip: int = 2          # Next IP to assign (10.100.0.X)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "group_secret": self.group_secret,
            "my_mesh_ip": self.my_mesh_ip,
            "next_ip": self.next_ip,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Network":
        return cls(
            name=data["name"],
            group_secret=data["group_secret"],
            my_mesh_ip=data["my_mesh_ip"],
            next_ip=data.get("next_ip", 2),
        )


@dataclass
class InviteCode:
    """Short invite code shared out-of-band.

    Format optimizations:
    - Network name: truncated to 16 chars max
    - Pubkey: full 44 chars (required for WireGuard)
    - Endpoint: IP:port
    - Auth token: 6 bytes = 8 chars base64
    - Assigned IP: just the last octet (assumes 10.100.0.X)
    - Relay mesh IP: optional, indicates this is a relay invite
    """

    network_name: str
    inviter_pubkey: str       # Inviter's WireGuard public key
    inviter_endpoint: str     # Inviter's external endpoint (ip:port) OR relay's endpoint
    auth_token: str           # One-time auth token (8 chars)
    assigned_ip: str          # Mesh IP assigned to joiner
    relay_mesh_ip: Optional[str] = None  # If set, this is a relay invite

    def encode(self) -> str:
        """Encode to a short string for sharing.

        Uses compact format:
        - Truncate network name to 16 chars
        - Store only last octet of mesh IP
        - Short auth token (8 chars)
        - Optional relay mesh IP last octet
        """
        # Truncate network name
        net_name = self.network_name[:16]

        # Extract last octet of IP (e.g., "10.100.0.5" -> "5")
        ip_octet = self.assigned_ip.split(".")[-1]

        # Add relay IP if present
        if self.relay_mesh_ip:
            relay_octet = self.relay_mesh_ip.split(".")[-1]
            data = f"{net_name}|{self.inviter_pubkey}|{self.inviter_endpoint}|{self.auth_token}|{ip_octet}|{relay_octet}"
        else:
            data = f"{net_name}|{self.inviter_pubkey}|{self.inviter_endpoint}|{self.auth_token}|{ip_octet}"

        encoded = base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
        return f"hm1_{encoded}"

    @classmethod
    def decode(cls, code: str) -> "InviteCode":
        """Decode from the short string format."""
        if not code.startswith("hm1_"):
            raise ValueError("Invalid invite code format")

        encoded = code[4:]  # Remove prefix
        # Add padding back
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding

        data = base64.urlsafe_b64decode(encoded).decode()
        parts = data.split("|")

        if len(parts) not in [5, 6]:
            raise ValueError("Invalid invite code format")

        # Reconstruct full mesh IP from last octet
        ip_octet = parts[4]
        full_ip = f"10.100.0.{ip_octet}"

        # Check for relay mesh IP (6th part)
        relay_mesh_ip = None
        if len(parts) == 6:
            relay_octet = parts[5]
            relay_mesh_ip = f"10.100.0.{relay_octet}"

        return cls(
            network_name=parts[0],
            inviter_pubkey=parts[1],
            inviter_endpoint=parts[2],
            auth_token=parts[3],
            assigned_ip=full_ip,
            relay_mesh_ip=relay_mesh_ip,
        )

    @classmethod
    def generate(cls, network_name: str, inviter_pubkey: str,
                 inviter_endpoint: str, assigned_ip: str) -> "InviteCode":
        """Generate a new invite code with random auth token."""
        return cls(
            network_name=network_name,
            inviter_pubkey=inviter_pubkey,
            inviter_endpoint=inviter_endpoint,
            auth_token=secrets.token_urlsafe(6),  # 6 bytes = 8 chars
            assigned_ip=assigned_ip,
        )


@dataclass
class NetworkBundle:
    """Full network bundle sent over WireGuard after handshake."""

    version: int
    network_name: str
    group_secret: str         # Encrypted with recipient's public key
    peers: list[Peer]
    invited_by: str

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "network_name": self.network_name,
            "group_secret": self.group_secret,
            "peers": [p.to_dict() for p in self.peers],
            "invited_by": self.invited_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NetworkBundle":
        return cls(
            version=data["version"],
            network_name=data["network_name"],
            group_secret=data["group_secret"],
            peers=[Peer.from_dict(p) for p in data["peers"]],
            invited_by=data["invited_by"],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, data: str) -> "NetworkBundle":
        return cls.from_dict(json.loads(data))


class MeshManager:
    """Manages the local mesh network state."""

    def __init__(self):
        self.identity: Optional[Identity] = None
        self.network: Optional[Network] = None
        self.peers: dict[str, Peer] = {}  # name -> Peer
        self._pending_invites: dict[str, InviteCode] = {}  # auth_token -> InviteCode

    def ensure_dirs(self):
        """Ensure mesh network directories exist."""
        NETWORK_DIR.mkdir(parents=True, exist_ok=True)
        PEERS_DIR.mkdir(parents=True, exist_ok=True)
        WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)

    def has_identity(self) -> bool:
        """Check if we have a local identity."""
        return (NETWORK_DIR / "identity.json").exists()

    def has_network(self) -> bool:
        """Check if we're part of a network."""
        return (NETWORK_DIR / "network.json").exists()

    def load_identity(self) -> Optional[Identity]:
        """Load identity from disk."""
        identity_file = NETWORK_DIR / "identity.json"
        if identity_file.exists():
            with open(identity_file) as f:
                self.identity = Identity.from_dict(json.load(f))
            return self.identity
        return None

    def save_identity(self, identity: Identity):
        """Save identity to disk."""
        self.ensure_dirs()
        self.identity = identity
        identity_file = NETWORK_DIR / "identity.json"
        with open(identity_file, "w") as f:
            json.dump(identity.to_dict(), f, indent=2)
        # Secure the file (private key!)
        os.chmod(identity_file, 0o600)

    def load_network(self) -> Optional[Network]:
        """Load network metadata from disk."""
        network_file = NETWORK_DIR / "network.json"
        if network_file.exists():
            with open(network_file) as f:
                self.network = Network.from_dict(json.load(f))
            return self.network
        return None

    def save_network(self, network: Network):
        """Save network metadata to disk."""
        self.ensure_dirs()
        self.network = network
        network_file = NETWORK_DIR / "network.json"
        with open(network_file, "w") as f:
            json.dump(network.to_dict(), f, indent=2)
        os.chmod(network_file, 0o600)

    def load_peers(self) -> dict[str, Peer]:
        """Load all peers from disk."""
        self.peers = {}
        if PEERS_DIR.exists():
            for peer_file in PEERS_DIR.glob("*.json"):
                with open(peer_file) as f:
                    peer = Peer.from_dict(json.load(f))
                    self.peers[peer.name] = peer
        return self.peers

    def save_peer(self, peer: Peer):
        """Save a peer to disk."""
        self.ensure_dirs()
        self.peers[peer.name] = peer
        peer_file = PEERS_DIR / f"{peer.name}.json"
        with open(peer_file, "w") as f:
            json.dump(peer.to_dict(), f, indent=2)

    def remove_peer(self, name: str):
        """Remove a peer."""
        if name in self.peers:
            del self.peers[name]
        peer_file = PEERS_DIR / f"{name}.json"
        if peer_file.exists():
            peer_file.unlink()

    def get_next_mesh_ip(self) -> str:
        """Get the next available mesh IP."""
        if not self.network:
            raise RuntimeError("Not part of a network")
        ip = f"10.100.0.{self.network.next_ip}"
        self.network.next_ip += 1
        self.save_network(self.network)
        return ip

    def create_network(self, name: str, group_secret: Optional[str] = None) -> Network:
        """Create a new mesh network (this node is the first peer)."""
        if self.has_network():
            raise RuntimeError("Already part of a network. Run 'homie network leave' first.")

        # Generate identity if needed
        if not self.has_identity():
            identity = Identity.generate()
            self.save_identity(identity)
        else:
            self.load_identity()

        # Create network with this node as first peer (IP .1)
        network = Network(
            name=name,
            group_secret=group_secret or secrets.token_urlsafe(16),
            my_mesh_ip="10.100.0.1",
            next_ip=2,
        )
        self.save_network(network)

        return network

    def create_invite(self, joiner_pubkey: str, joiner_name: str,
                      my_endpoint: str) -> InviteCode:
        """Create an invite code for a new peer."""
        if not self.network or not self.identity:
            raise RuntimeError("Not part of a network")

        assigned_ip = self.get_next_mesh_ip()

        invite = InviteCode.generate(
            network_name=self.network.name,
            inviter_pubkey=self.identity.public_key,
            inviter_endpoint=my_endpoint,
            assigned_ip=assigned_ip,
        )

        # Store pending invite
        self._pending_invites[invite.auth_token] = invite

        # Pre-register the peer (will be confirmed when they connect)
        peer = Peer(
            name=joiner_name,
            public_key=joiner_pubkey,
            mesh_ip=assigned_ip,
            endpoints=[],
            invited_by=self.network.my_mesh_ip,
        )
        self.save_peer(peer)

        return invite

    def create_bundle_for_joiner(self, joiner_pubkey: str) -> NetworkBundle:
        """Create a network bundle to send to a joining peer."""
        if not self.network or not self.identity:
            raise RuntimeError("Not part of a network")

        # Load all peers
        self.load_peers()

        # Include ourselves in the peer list
        my_peer = Peer(
            name=os.environ.get("USER", "homie"),  # TODO: get from config
            public_key=self.identity.public_key,
            mesh_ip=self.network.my_mesh_ip,
            endpoints=[],  # TODO: add our endpoint
        )

        all_peers = [my_peer] + list(self.peers.values())

        return NetworkBundle(
            version=1,
            network_name=self.network.name,
            group_secret=self.network.group_secret,  # TODO: encrypt with joiner's key
            peers=all_peers,
            invited_by=my_peer.name,
        )

    def join_network(self, invite: InviteCode, bundle: NetworkBundle):
        """Join a network using an invite code and bundle."""
        if self.has_network():
            raise RuntimeError("Already part of a network. Run 'homie network leave' first.")

        # Generate identity if needed
        if not self.has_identity():
            identity = Identity.generate()
            self.save_identity(identity)

        # Create network
        network = Network(
            name=bundle.network_name,
            group_secret=bundle.group_secret,
            my_mesh_ip=invite.assigned_ip,
            next_ip=len(bundle.peers) + 2,  # Next available after all existing peers
        )
        self.save_network(network)

        # Save all peers from bundle
        for peer in bundle.peers:
            self.save_peer(peer)

    def leave_network(self):
        """Leave the current network."""
        # Remove network file
        network_file = NETWORK_DIR / "network.json"
        if network_file.exists():
            network_file.unlink()

        # Remove all peers
        if PEERS_DIR.exists():
            for peer_file in PEERS_DIR.glob("*.json"):
                peer_file.unlink()

        self.network = None
        self.peers = {}

    def get_external_endpoint(self) -> Optional[str]:
        """
        Try to determine our external endpoint for WireGuard.

        Uses STUN and other methods to auto-detect the best endpoint.
        """
        from . import stun

        endpoint_info = stun.detect_public_endpoint(WIREGUARD_PORT)
        if endpoint_info:
            return f"{endpoint_info.ip}:{endpoint_info.port}"

        return None

    def get_best_endpoint(self) -> tuple[Optional[str], str]:
        """
        Detect the best endpoint using tiered fallback strategy.

        Returns:
            (endpoint, method) where method is one of:
            - "lan": Same local network
            - "stun": STUN-detected public IP
            - "tailscale": Tailscale IP
            - "relay": Must use mesh relay
            - "manual": No automatic method available
        """
        from . import stun
        from .utils import get_local_ip

        # Tier 1: Check if on same LAN (would need joiner's IP - skip for now)
        # This is checked in the CLI when we know both IPs

        # Tier 2: Try STUN
        endpoint_info = stun.detect_public_endpoint(WIREGUARD_PORT)
        if endpoint_info:
            if endpoint_info.method == "tailscale":
                return (f"{endpoint_info.ip}:{endpoint_info.port}", "tailscale")
            elif endpoint_info.reliability >= 70:
                # Good enough for direct connection
                return (f"{endpoint_info.ip}:{endpoint_info.port}", "stun")

        # Tier 3: Check for relay peers
        relay_peers = self.find_relay_peers()
        if relay_peers:
            return (None, "relay")  # Endpoint will be relay's endpoint

        # Tier 4: No automatic method
        return (None, "manual")

    def find_relay_peers(self) -> list[Peer]:
        """
        Find peers in the mesh that can act as relays.

        Returns list of peers with public endpoints, sorted by reliability.
        """
        self.load_peers()

        relay_peers = []
        for peer in self.peers.values():
            # Peer must have endpoints configured
            if peer.endpoints:
                relay_peers.append(peer)

        return relay_peers

    def create_invite_via_relay(self, joiner_pubkey: str, joiner_name: str,
                                relay_peer: Peer) -> InviteCode:
        """
        Create an invite that uses a relay peer for coordination.

        Args:
            joiner_pubkey: Joiner's WireGuard public key
            joiner_name: Name for the joiner
            relay_peer: Peer that will relay the invite

        Returns:
            InviteCode with relay information
        """
        if not self.network or not self.identity:
            raise RuntimeError("Not part of a network")

        assigned_ip = self.get_next_mesh_ip()

        # Create invite with relay's endpoint
        invite = InviteCode(
            network_name=self.network.name,
            inviter_pubkey=self.identity.public_key,
            inviter_endpoint=relay_peer.endpoints[0],  # Relay's public endpoint
            auth_token=secrets.token_urlsafe(6),
            assigned_ip=assigned_ip,
            relay_mesh_ip=relay_peer.mesh_ip  # Indicates this is a relay invite
        )

        # Pre-register the peer
        peer = Peer(
            name=joiner_name,
            public_key=joiner_pubkey,
            mesh_ip=assigned_ip,
            endpoints=[],
            invited_by=self.network.my_mesh_ip,
        )
        self.save_peer(peer)

        return invite

    def register_with_relay(self, relay_peer: Peer, invite: InviteCode):
        """
        Register an invite with a relay peer.

        Sends HTTP request to relay peer's relay service to store the invite.
        """
        import requests

        try:
            response = requests.post(
                f"http://{relay_peer.mesh_ip}:8080/register",
                json={
                    "token": invite.auth_token,
                    "inviter_mesh_ip": self.network.my_mesh_ip,
                    "inviter_pubkey": self.identity.public_key
                },
                timeout=5
            )

            if response.status_code != 201:
                raise RuntimeError(f"Relay registration failed: {response.status_code}")

        except Exception as e:
            raise RuntimeError(f"Failed to contact relay peer: {e}")

    def lookup_via_relay(self, relay_mesh_ip: str, token: str) -> Optional[dict]:
        """
        Look up invite information via relay peer.

        Args:
            relay_mesh_ip: Mesh IP of the relay peer
            token: Auth token from invite code

        Returns:
            Dict with inviter_mesh_ip and inviter_pubkey, or None if not found
        """
        import requests

        try:
            response = requests.get(
                f"http://{relay_mesh_ip}:8080/lookup",
                params={"token": token},
                timeout=5
            )

            if response.status_code == 200:
                return response.json()

        except Exception:
            pass

        return None

    # =========================================================================
    # WireGuard Tunnel Management
    # =========================================================================

    def generate_wireguard_config(self) -> Path:
        """Generate WireGuard configuration file from network state.

        Returns:
            Path to the generated config file at ~/.homie/wireguard/homie0.conf
        """
        if not self.identity or not self.network:
            raise RuntimeError("No identity or network configured")

        self.load_peers()

        config_lines = [
            "[Interface]",
            f"PrivateKey = {self.identity.private_key}",
            f"Address = {self.network.my_mesh_ip}/16",
            f"ListenPort = {WIREGUARD_PORT}",
            "",
        ]

        # Add each peer section
        for peer in self.peers.values():
            config_lines.append("[Peer]")
            config_lines.append(f"PublicKey = {peer.public_key}")
            config_lines.append(f"AllowedIPs = {peer.mesh_ip}/32")
            if peer.endpoints:
                config_lines.append(f"Endpoint = {peer.endpoints[0]}")
            config_lines.append("PersistentKeepalive = 25")
            config_lines.append("")

        # Write config file with secure permissions
        config_path = WIREGUARD_DIR / f"{INTERFACE_NAME}.conf"
        WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
        config_path.write_text("\n".join(config_lines))
        os.chmod(config_path, 0o600)

        return config_path

    def tunnel_up(self) -> bool:
        """Bring up the WireGuard tunnel using wg-quick.

        Requires sudo. The user will be prompted for their password inline.

        Returns:
            True if successful, False otherwise.

        Raises:
            RuntimeError: If wg-quick is not installed.
        """
        # Generate/update config first
        config_path = self.generate_wireguard_config()

        # Check if already up
        if self.is_tunnel_up():
            # Bring down first to apply any config changes
            self.tunnel_down()

        try:
            # Let sudo prompt interactively for password
            result = subprocess.run(
                ["sudo", "wg-quick", "up", str(config_path)],
                timeout=60,
            )
            if result.returncode == 0:
                return True

            # If it failed because interface exists, try bringing down first
            # This handles edge cases where is_tunnel_up() returned False but interface exists
            self.tunnel_down()
            result = subprocess.run(
                ["sudo", "wg-quick", "up", str(config_path)],
                timeout=60,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            raise RuntimeError(
                "wg-quick not found. Install WireGuard tools:\n"
                "  macOS:  brew install wireguard-tools\n"
                "  Linux:  sudo apt install wireguard-tools"
            )

    def tunnel_down(self) -> bool:
        """Bring down the WireGuard tunnel.

        Returns:
            True if successful or tunnel was not up.
        """
        config_path = WIREGUARD_DIR / f"{INTERFACE_NAME}.conf"

        if not config_path.exists():
            return True  # Nothing to bring down

        try:
            # Always try to bring down - don't check is_tunnel_up() first
            # as the check can be unreliable on macOS
            result = subprocess.run(
                ["sudo", "wg-quick", "down", str(config_path)],
                timeout=30,
            )
            # Return True if successful OR if it was already down (exit code varies)
            return True
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            # If wg-quick down fails, tunnel is likely already down
            return True

    def is_tunnel_up(self) -> bool:
        """Check if the WireGuard tunnel interface exists and is up."""
        try:
            # Use 'wg show' without sudo first - it can show interface names without root
            # On macOS, the interface shows up as utunX but wg-quick tracks it
            result = subprocess.run(
                ["wg", "show", "interfaces"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                interfaces = result.stdout.decode().strip().split()
                # Check if our interface name is in the list
                if INTERFACE_NAME in interfaces:
                    return True

            # Fallback: check if the config is tracked by wg-quick on macOS
            # wg-quick on macOS stores state in /var/run/wireguard/
            import platform
            if platform.system() == "Darwin":
                state_file = Path(f"/var/run/wireguard/{INTERFACE_NAME}.name")
                if state_file.exists():
                    return True

            return False
        except Exception:
            return False
