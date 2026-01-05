"""
STUN client and endpoint detection for Homie mesh networking.

This module provides automatic detection of the best endpoint for WireGuard connections:
- Same LAN detection (fastest, zero config)
- STUN-based public IP discovery
- Tailscale IP detection
- NAT type classification
"""

import socket
import struct
import subprocess
from dataclasses import dataclass
from typing import Optional
import urllib.request


@dataclass
class EndpointInfo:
    """Information about a detected endpoint."""

    ip: str
    port: int
    method: str  # "lan", "stun", "tailscale", "public"
    nat_type: Optional[str] = None
    reliability: int = 0  # 0-100 score


def check_same_lan(ip1: str, ip2: str) -> bool:
    """Check if two IPs are on the same local network."""
    # Common private IP ranges
    def is_private(ip: str) -> bool:
        parts = ip.split('.')
        if len(parts) != 4:
            return False

        first = int(parts[0])
        second = int(parts[1])

        # 10.0.0.0/8
        if first == 10:
            return True
        # 172.16.0.0/12
        if first == 172 and 16 <= second <= 31:
            return True
        # 192.168.0.0/16
        if first == 192 and second == 168:
            return True

        return False

    if not (is_private(ip1) and is_private(ip2)):
        return False

    # Check if same /24 subnet (simple heuristic)
    parts1 = ip1.split('.')
    parts2 = ip2.split('.')

    # Same first 3 octets = likely same LAN
    return parts1[:3] == parts2[:3]


def check_tailscale_ip() -> Optional[str]:
    """Check if Tailscale is running and get the Tailscale IP."""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            timeout=2,
            text=True
        )

        if result.returncode == 0:
            ip = result.stdout.strip()
            # Tailscale uses 100.64.0.0/10
            if ip and ip.startswith("100."):
                return ip
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def get_public_ip() -> Optional[str]:
    """Get public IP from web services (fallback method)."""
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]

    for service in services:
        try:
            with urllib.request.urlopen(service, timeout=3) as response:
                ip = response.read().decode().strip()

                # Basic IPv4 validation
                parts = ip.split('.')
                if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                    return ip
        except Exception:
            continue

    return None


def stun_query(stun_host: str = "stun.l.google.com", stun_port: int = 19302,
               local_port: int = 51820) -> Optional[tuple[str, int]]:
    """
    Query STUN server to discover external IP and port.

    Returns:
        (external_ip, external_port) or None if failed
    """
    # STUN Binding Request message
    # Format: Type (2 bytes) | Length (2 bytes) | Magic Cookie (4 bytes) | Transaction ID (12 bytes)
    message_type = 0x0001  # Binding Request
    message_length = 0x0000
    magic_cookie = 0x2112A442
    transaction_id = struct.pack('!12s', b'\x00' * 12)  # Simplified - should be random

    request = struct.pack('!HHI', message_type, message_length, magic_cookie) + transaction_id

    try:
        # Create UDP socket bound to WireGuard port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)

        try:
            sock.bind(('', local_port))
        except OSError:
            # Port already in use, use random port
            sock.bind(('', 0))

        # Send STUN request
        sock.sendto(request, (stun_host, stun_port))

        # Receive response
        data, addr = sock.recvfrom(1024)
        sock.close()

        # Parse STUN response (simplified)
        if len(data) < 20:
            return None

        # Look for MAPPED-ADDRESS or XOR-MAPPED-ADDRESS attribute
        offset = 20  # Skip STUN header

        while offset < len(data):
            if offset + 4 > len(data):
                break

            attr_type, attr_length = struct.unpack('!HH', data[offset:offset+4])
            offset += 4

            if offset + attr_length > len(data):
                break

            # XOR-MAPPED-ADDRESS (0x0020)
            if attr_type == 0x0020 and attr_length >= 8:
                # Parse XOR-MAPPED-ADDRESS
                family = data[offset + 1]
                if family == 0x01:  # IPv4
                    port_xor = struct.unpack('!H', data[offset+2:offset+4])[0]
                    ip_xor = struct.unpack('!I', data[offset+4:offset+8])[0]

                    # XOR with magic cookie
                    port = port_xor ^ (magic_cookie >> 16)
                    ip = ip_xor ^ magic_cookie

                    # Convert IP to string
                    ip_str = socket.inet_ntoa(struct.pack('!I', ip))

                    return (ip_str, port)

            # MAPPED-ADDRESS (0x0001) - legacy
            elif attr_type == 0x0001 and attr_length >= 8:
                family = data[offset + 1]
                if family == 0x01:  # IPv4
                    port = struct.unpack('!H', data[offset+2:offset+4])[0]
                    ip_bytes = data[offset+4:offset+8]
                    ip_str = socket.inet_ntoa(ip_bytes)

                    return (ip_str, port)

            offset += attr_length
            # Attributes are padded to 4-byte boundary
            offset += (4 - (attr_length % 4)) % 4

        return None

    except Exception:
        return None


def detect_nat_type() -> str:
    """
    Detect NAT type (simplified classification).

    Returns:
        "Full Cone", "Restricted Cone", "Port Restricted", "Symmetric", or "Unknown"
    """
    # This is a simplified version
    # Full NAT type detection requires multiple STUN queries to different servers

    result1 = stun_query("stun.l.google.com", 19302)
    if not result1:
        return "Unknown"

    result2 = stun_query("stun1.l.google.com", 19302)
    if not result2:
        return "Unknown"

    # If external port is the same for both queries, likely Full or Restricted Cone
    if result1[1] == result2[1]:
        return "Restricted Cone"  # Conservative estimate
    else:
        return "Symmetric"  # Different ports = Symmetric NAT


def detect_public_endpoint(local_port: int = 51820) -> Optional[EndpointInfo]:
    """
    Detect the best public endpoint using multiple methods.

    Tries in order:
    1. Tailscale IP (most reliable for remote)
    2. STUN (automatic NAT traversal)
    3. Public IP services (requires manual port forward)

    Returns:
        EndpointInfo with detected endpoint and reliability score
    """

    # Method 1: Check Tailscale (best for remote connections)
    ts_ip = check_tailscale_ip()
    if ts_ip:
        return EndpointInfo(
            ip=ts_ip,
            port=local_port,
            method="tailscale",
            reliability=100
        )

    # Method 2: Try STUN
    stun_result = stun_query(local_port=local_port)
    if stun_result:
        nat_type = detect_nat_type()

        # Reliability based on NAT type
        reliability_map = {
            "Full Cone": 95,
            "Restricted Cone": 85,
            "Port Restricted": 50,
            "Symmetric": 20,
            "Unknown": 60,
        }

        return EndpointInfo(
            ip=stun_result[0],
            port=stun_result[1],
            method="stun",
            nat_type=nat_type,
            reliability=reliability_map.get(nat_type, 60)
        )

    # Method 3: Public IP services (low reliability without port forward)
    public_ip = get_public_ip()
    if public_ip:
        return EndpointInfo(
            ip=public_ip,
            port=local_port,
            method="public",
            reliability=30  # Requires manual port forward
        )

    return None
