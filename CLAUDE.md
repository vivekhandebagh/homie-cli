# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Homie Compute is a peer-to-peer distributed compute CLI for running scripts on friends' idle machines over a local network. No cloud infrastructure—just UDP discovery and TCP job execution with Docker sandboxing.

## Commands

```bash
# Install in development mode
pip install -e .

# Initial setup (interactive wizard)
homie setup

# Start daemon (discovery + worker)
homie up
homie up --mesh              # With WireGuard mesh for remote peers

# List available peers
homie peers

# Run a script on a peer
homie run script.py --on <peer-name> [--image <docker-image>] [--files file1,file2]

# Manage Docker environments
homie env list
homie env add <name> <docker-image>

# View/edit configuration
homie config show
homie config set <key> <value>

# Mesh network management (for remote peers across internet)
homie network create <name>  # Create new mesh network
homie network join           # Generate public key for joining
homie network join <code>    # Join with invite code
homie network invite         # Create invite for new peer
homie network status         # Show network and peers
homie network up             # Bring up WireGuard tunnel manually
homie network down           # Tear down WireGuard tunnel
homie network leave          # Leave the mesh network
```

**Requirements:** Python 3.10+, Docker, WireGuard (for mesh networking)

## Architecture

The system uses a P2P model with three core components:

1. **Discovery** (`discovery.py`): UDP broadcast on port 5555 every 2 seconds with HMAC-signed heartbeats containing system stats. Peers timeout after 10 seconds.

2. **Worker** (`worker.py` + `container.py`): TCP server on port 5556 accepting job submissions. Executes jobs in Docker containers with strict limits (no network, 2 CPU cores, 4GB RAM, 600s timeout).

3. **Client** (`client.py` + `jobs.py`): Sends jobs to workers over TCP. Jobs are JSON with base64-encoded code/files. Authentication via HMAC-SHA256 on job ID + timestamp (5-minute window).

**Data Flow:**
```
homie up → starts Discovery thread (UDP broadcast) + Worker thread (TCP server)
homie run → Client connects to peer's Worker → Worker spawns Docker container → streams output back
```

## Key Modules

| File | Purpose |
|------|---------|
| `cli.py` | Click command definitions (main entry point) |
| `discovery.py` | UDP peer discovery and heartbeat broadcasting |
| `worker.py` | TCP server that receives and executes jobs |
| `container.py` | Docker container lifecycle management |
| `jobs.py` | Job serialization, deserialization, and HMAC auth |
| `client.py` | TCP client for submitting jobs to workers |
| `history.py` | Job history tracking (JSONL format) |
| `config.py` | Config management (~/.homie/config.yaml) |
| `mesh.py` | WireGuard mesh network management |
| `ui.py` | Rich terminal UI components and animations |
| `utils.py` | System monitoring (CPU, RAM, GPU) |

## Wire Protocol

Binary message format: `type (1 byte) + length (4 bytes) + data`
- `J`: Job submission
- `O`: stdout chunk
- `E`: stderr chunk

## File Locations

- Config: `~/.homie/config.yaml`
- History: `~/.homie/job_history.jsonl`
- Peer cache: `~/.homie/peer_cache.json`
- Mesh identity: `~/.homie/network/identity.json`
- Mesh network: `~/.homie/network/network.json`
- Mesh peers: `~/.homie/network/peers/*.json`
- WireGuard config: `~/.homie/wireguard/homie0.conf`

## Adding New CLI Commands

Add to `cli.py`. Example pattern:

```python
@cli.command()
@click.option('--flag', help='Description')
def mycommand(flag):
    """Command description."""
    config = Config.load()
    # implementation
```

## Security Model

- **Group secret**: Shared key for HMAC authentication
- **Docker isolation**: No network access, resource limits, non-root user
- **Timestamp validation**: 5-minute window prevents replay attacks

## Testing

No automated tests configured. Manual testing workflow:
1. Run `homie setup` on two machines on same network
2. Start `homie up` on both
3. Verify `homie peers` shows both machines
4. Test `homie run` with a simple script
