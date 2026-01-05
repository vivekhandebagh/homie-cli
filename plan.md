# Homie Compute - WireGuard Mesh Implementation Plan

## Current State

Homie Compute is a P2P distributed compute CLI. The **local network** functionality is complete:
- UDP discovery, TCP job execution, Docker isolation, streaming output
- ~4,700 lines of Python across 11 modules

The **remote networking** has two approaches:
1. **Tailscale** - Works today (manual IP exchange via `homie add`)
2. **Native WireGuard Mesh** - Partially implemented, needs completion

---

## WireGuard Mesh: What's Done vs TODO

### Done

| Component | Location | Status |
|-----------|----------|--------|
| Data structures (Identity, Peer, Network, InviteCode, NetworkBundle) | `mesh.py:35-289` | Complete |
| Key generation (wg command + Python X25519 fallback) | `mesh.py:43-101` | Complete |
| Invite code encode/decode (~50 chars) | `mesh.py:174-251` | Complete |
| MeshManager persistence (identity, network, peers) | `mesh.py:291-507` | Complete |
| WireGuard config generation | `mesh.py:513-548` | Complete |
| Tunnel up/down/status | `mesh.py:550-635` | Complete |
| CLI: `homie network create/invite/join/status/leave/up/down` | `cli.py:853-1227` | Partial |
| Integration with `homie up --mesh` | `cli.py:127-211` | Complete |

### TODO - Critical Path

| Component | Priority | Complexity | Description |
|-----------|----------|------------|-------------|
| Bundle transfer protocol | P0 | Medium | TCP server/client for sending NetworkBundle over WireGuard |
| Inviter listener | P0 | Medium | Wait for joiner connection, verify auth token, send bundle |
| Joiner connector | P0 | Medium | Connect to inviter, receive bundle, import peers |
| Group secret transfer | P0 | Low | Currently "pending" - joiner can't authenticate jobs |

### TODO - Nice to Have

| Component | Priority | Complexity | Description |
|-----------|----------|------------|-------------|
| Gossip protocol | P1 | High | Announce new peers to existing peers |
| External endpoint detection | P2 | Medium | STUN-like discovery for public IP |
| NAT relay | P2 | High | Route through reachable peer when direct fails |
| Bundle encryption | P3 | Low | Encrypt group_secret with joiner's public key |

---

## The Problem Right Now

When Bob tries to join Alice's network:

```
1. Alice: homie network create my-crew     ✅ Works
2. Bob:   homie network join               ✅ Gets public key
3. Alice: homie network invite             ✅ Creates invite code
4. Bob:   homie network join <code>        ❌ BROKEN
   - Saves Alice as single peer
   - group_secret = "pending"
   - Doesn't receive other peers
5. Both:  homie up --mesh                  ✅ Tunnel comes up
6. Bob:   homie run script.py              ❌ Auth fails (wrong group_secret)
```

---

## Implementation Plan

### Phase 1: Bundle Transfer Protocol (P0)

**Goal:** When joiner runs `homie network join <code>`, they connect to inviter and receive the full bundle.

#### 1.1 Add Bundle Server to MeshManager

**File:** `homie/mesh.py`

Add a simple TCP server that:
- Listens on a port (e.g., 51821) for incoming bundle requests
- Verifies the auth token from the invite code
- Sends the NetworkBundle as JSON over the connection

```python
# Add to MeshManager class

BUNDLE_PORT = 51821

def start_bundle_server(self, expected_token: str, timeout: int = 300) -> Optional[NetworkBundle]:
    """Start a TCP server to send bundle to joiner.

    Args:
        expected_token: The auth token from the invite code
        timeout: How long to wait for joiner (seconds)

    Returns:
        The bundle that was sent, or None if timeout/error
    """
    # Create TCP socket
    # Listen on 0.0.0.0:BUNDLE_PORT
    # Accept one connection
    # Receive auth token, verify it matches expected_token
    # Send NetworkBundle as JSON
    # Close connection
    pass

def fetch_bundle_from_inviter(self, invite: InviteCode) -> NetworkBundle:
    """Connect to inviter and fetch the network bundle.

    Args:
        invite: The decoded invite code

    Returns:
        The network bundle from the inviter

    Raises:
        ConnectionError: If can't reach inviter
        AuthError: If auth token rejected
    """
    # Parse endpoint from invite (ip:wireguard_port)
    # Connect to inviter's bundle port (ip:BUNDLE_PORT)
    # Send auth token
    # Receive NetworkBundle JSON
    # Parse and return
    pass
```

#### 1.2 Update CLI Invite Command

**File:** `homie/cli.py` (around line 903)

```python
@network.command("invite")
def network_invite():
    # ... existing code to create invite ...

    console.print(f"Waiting for [cyan]{joiner_name}[/] to connect...")
    console.print("[dim]Press Ctrl+C to cancel[/]")

    # NEW: Start bundle server and wait
    try:
        bundle = mesh.create_bundle_for_joiner(joiner_pubkey)
        result = mesh.start_bundle_server(invite.auth_token, timeout=300)
        if result:
            console.print(f"[green]✓[/] Bundle sent to {joiner_name}")
            # Regenerate WireGuard config with new peer
            mesh.generate_wireguard_config()
        else:
            console.print("[yellow]Timeout waiting for joiner[/]")
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled. Invite code still valid.[/]")
```

#### 1.3 Update CLI Join Command

**File:** `homie/cli.py` (around line 977)

```python
@network.command("join")
@click.argument("invite_code", required=False)
def network_join(invite_code: str):
    # ... existing code to parse invite ...

    console.print("Connecting to inviter...")

    # NEW: Fetch bundle from inviter
    try:
        bundle = mesh.fetch_bundle_from_inviter(invite)
        mesh.join_network(invite, bundle)
        console.print(f"[green]✓[/] Joined network: {bundle.network_name}")
        console.print(f"[dim]Received {len(bundle.peers)} peers[/]")
    except ConnectionError as e:
        console.print(f"[red]Could not reach inviter: {e}[/]")
        console.print("[dim]Make sure they're running 'homie network invite'[/]")
        sys.exit(1)
```

#### 1.4 Wire Protocol

Simple JSON over TCP:

```
Joiner -> Inviter:
{
  "type": "bundle_request",
  "auth_token": "xK7mQ9...",
  "public_key": "Yj7KLm2x..."
}

Inviter -> Joiner:
{
  "type": "bundle_response",
  "success": true,
  "bundle": { ... NetworkBundle ... }
}
```

---

### Phase 2: Testing & Edge Cases

#### 2.1 Test Scenarios

1. **Happy path:** Alice invites, Bob joins, both `homie up --mesh`, Bob runs job on Alice
2. **Inviter offline:** Bob tries to join but Alice isn't running invite command
3. **Wrong auth token:** Malicious actor tries to get bundle with guessed token
4. **Timeout:** Inviter waits 5 minutes, no one joins
5. **Multiple peers:** Alice has 3 peers, invites Bob, Bob gets all 4 peers in bundle

#### 2.2 Error Handling

- Connection refused -> "Inviter not ready. Ask them to run 'homie network invite'"
- Auth token mismatch -> "Invalid invite code"
- Timeout -> "Inviter didn't respond in time"
- Malformed bundle -> "Received invalid data from inviter"

---

### Phase 3: Gossip Protocol (P1)

**Goal:** When a new peer joins, announce them to all existing peers.

#### 3.1 Peer Announcement Message

```python
@dataclass
class PeerAnnouncement:
    """Announce a new peer to the network."""
    type: str = "peer_announce"
    peer: Peer
    announced_by: str  # Name of peer making announcement
    signature: str     # HMAC signature using group_secret
```

#### 3.2 Announcement Flow

1. When inviter sends bundle to joiner successfully:
   - Create PeerAnnouncement for the new joiner
   - Send to all known peers over WireGuard mesh

2. When a peer receives PeerAnnouncement:
   - Verify signature
   - Add peer to local peer list
   - Regenerate WireGuard config
   - Optionally restart tunnel to apply changes

#### 3.3 Implementation Location

**File:** `homie/mesh.py`

```python
def announce_peer(self, peer: Peer) -> None:
    """Announce a new peer to all known peers."""
    pass

def handle_peer_announcement(self, announcement: PeerAnnouncement) -> None:
    """Handle incoming peer announcement."""
    pass
```

**File:** `homie/cli.py` - Add announcement after successful invite

---

### Phase 4: Robustness (P2)

#### 4.1 External Endpoint Detection

Use STUN-like protocol to discover public IP:

```python
def get_external_endpoint(self) -> Optional[str]:
    """Discover our external IP:port using STUN."""
    # Try common STUN servers
    # stun.l.google.com:19302
    # stun.cloudflare.com:3478
    pass
```

#### 4.2 NAT Relay

If peer A can't reach peer C directly, but both can reach peer B:
- Route A->C traffic through B
- Requires B to act as WireGuard relay
- Complex - defer to P2

---

## File Changes Summary

| File | Changes |
|------|---------|
| `homie/mesh.py` | Add `start_bundle_server()`, `fetch_bundle_from_inviter()`, `announce_peer()` |
| `homie/cli.py` | Update `network_invite` and `network_join` commands |
| `homie/discovery.py` | Minor: ensure mesh IPs work with direct peers |

---

## Testing Checklist

### Local Testing (Same Machine)

```bash
# Terminal 1: Create network
homie network create test-net
homie network invite
# Enter a test public key, get invite code

# Terminal 2: Join network
homie network join
# Get public key, give to terminal 1
homie network join <invite_code>

# Verify
homie network status  # Both terminals should show each other
```

### Remote Testing (Two Machines)

```bash
# Machine A (inviter)
homie network create my-crew
homie network invite
# Wait for machine B

# Machine B (joiner)
homie network join
# Share public key with A
homie network join <invite_code_from_A>

# Both machines
homie up --mesh
homie peers  # Should see each other

# Machine B
echo "print('hello from mesh')" > test.py
homie run test.py  # Should run on Machine A
```

---

## Dependencies

No new dependencies required. Uses:
- `socket` (stdlib) - TCP server/client
- `json` (stdlib) - Bundle serialization
- `threading` (stdlib) - Server timeout handling

---

## Timeline Estimate

| Phase | Effort | Description |
|-------|--------|-------------|
| Phase 1 | 2-3 hours | Bundle transfer - makes join actually work |
| Phase 2 | 1 hour | Testing and error handling |
| Phase 3 | 2-3 hours | Gossip protocol - multi-peer networks |
| Phase 4 | 4+ hours | NAT traversal - complex networking |

**Recommended order:** Phase 1 -> Phase 2 -> Test with real users -> Phase 3 -> Phase 4

---

## Quick Start: What to Implement First

1. **`mesh.py:start_bundle_server()`** - 50 lines, TCP server that sends bundle
2. **`mesh.py:fetch_bundle_from_inviter()`** - 40 lines, TCP client that receives bundle
3. **`cli.py:network_invite`** - 20 lines, call bundle server after creating invite
4. **`cli.py:network_join`** - 20 lines, call fetch_bundle after parsing invite

Total: ~130 lines of new code to make join work end-to-end.
