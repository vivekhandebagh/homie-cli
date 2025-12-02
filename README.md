# 🏠 Homie Compute
```
    __  ______  __  _____________    _____________
   / / / / __ \/  |/  /  _/ ____/   /  ____// __  \
  / /_/ / / / / /|_/ // // __/     /  /    / / /  /
 / __  / /_/ / /  / // // /___    /  /___ / /_/  /
/_/ /_/\____/_/  /_/___/_____/   /_______/\_____/ mpute
```
> P2P distributed compute for friends on the same network.

You and your friends are on the same wifi. Each person has a laptop/desktop with varying specs. Someone has a beefy GPU, someone else has tons of RAM. When you need to run something heavy, why not use your homies' idle machines?

**No cloud, no servers, no accounts. Just a CLI tool and your local network.**

```
┌─────────────┐     UDP broadcast      ┌─────────────┐
│   raj's     │ ◄──────────────────►   │   mike's    │
│   machine   │      "i'm alive"       │   machine   │
└─────────────┘                        └─────────────┘
       ▲                                      ▲
       │           UDP broadcast              │
       └──────────────► ◄─────────────────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │   your      │
                 │   machine   │
                 └─────────────┘
```

## Quick Start

```bash
# Install
pip install -e .

# Setup (first time only)
homie setup

# Start the daemon
homie up

# See who's online
homie peers

# Run a script on a friend's machine
homie run train.py --epochs 10
```

## Features

- **Auto-discovery** - Finds peers automatically via UDP broadcast
- **Secure execution** - Jobs run in Docker containers with resource limits
- **GPU support** - Pass `--gpu` to run on a machine with a GPU
- **Beautiful CLI** - Live dashboard showing all peers and their resources
- **Simple auth** - Shared secret keeps random devices out

## Commands

| Command | Description |
|---------|-------------|
| `homie up` | Start daemon (discovery + worker) |
| `homie up -f` | Start with live dashboard |
| `homie peers` | List all peers on network |
| `homie run script.py` | Run on best available peer |
| `homie run -n raj script.py` | Run on specific peer |
| `homie run --gpu train.py` | Run on peer with GPU |
| `homie run -f data.csv script.py` | Include additional files |
| `homie config` | Show current configuration |
| `homie whoami` | Show your identity |

## Example Session

```bash
# Terminal 1 - raj's machine
$ homie up
╭──────────────────────────────────────╮
│  🏠 HOMIE COMPUTE                    │
│  Name: raj                           │
│  IP: 192.168.1.42                    │
│  CPU: 8 cores │ RAM: 32 GB           │
│  GPU: RTX 3080 (10 GB)               │
╰──────────────────────────────────────╯
  ✓ Docker sandbox ready
  ✓ Discovery broadcasting
  ✓ Worker listening

# Terminal 2 - your machine
$ homie peers
╭────────────────────────────────────────────────────────╮
│                  🏠 HOMIES ON NETWORK                  │
├──────────┬──────────────┬───────┬────────┬────────────┤
│ NAME     │ IP           │ CPU   │ RAM    │ GPU        │
├──────────┼──────────────┼───────┼────────┼────────────┤
│ raj      │ 192.168.1.42 │ 23% ▓░│ 24.1GB │ RTX 3080   │
│ mike     │ 192.168.1.43 │ 12% ░░│ 8.2 GB │ -          │
╰──────────┴──────────────┴───────┴────────┴────────────╯

$ homie run train.py --epochs 10
╭─ Sending to raj (best available) ────────────────────╮
│ Job ID: a1b2c3d4                                     │
│ Script: train.py                                     │
╰──────────────────────────────────────────────────────╯

[raj] Loading data...
[raj] Epoch 1/10 - loss: 0.452
[raj] Epoch 2/10 - loss: 0.321
...
[raj] ✓ Saved model.pt

╭─ Job Complete ───────────────────────────────────────╮
│ Runtime: 3m 24s                                      │
│ Downloaded: model.pt                                 │
╰──────────────────────────────────────────────────────╯
```

## Requirements

- Python 3.10+
- Docker (for running jobs securely)
- Same local network as your friends

## How It Works

1. **Discovery**: Peers broadcast their existence via UDP every 2 seconds
2. **Authentication**: Heartbeats are signed with a shared group secret
3. **Job submission**: You send code to a peer over TCP
4. **Sandboxed execution**: Code runs in a Docker container with:
   - No network access
   - Limited CPU/RAM
   - Isolated filesystem
   - Non-root user
5. **Results**: Output streams back, files are transferred when done

## Security

This is designed for **trusted friends on a trusted network**. The security model:

| What's Protected | How |
|------------------|-----|
| Random devices joining | Group secret (HMAC) |
| Malicious code damaging host | Docker container isolation |
| Resource exhaustion | CPU, RAM, process limits |
| Network exfiltration | No network in container |

**⚠️ Only run this on networks you trust with people you trust.**

## Configuration

Config is stored in `~/.homie/config.yaml`:

```yaml
name: raj
group_secret: your-shared-secret
discovery_port: 5555
worker_port: 5556
container_cpu_limit: 2.0
container_memory_limit: 4g
container_timeout: 600
```

### Setting Resource Limits

Control how much of your machine friends can use:

```bash
# Set CPU cores (e.g., 2 cores, 4 cores, 0.5 for half a core)
homie config --cpu 4

# Set memory limit (e.g., 4g, 8g, 16g)
homie config --memory 8g

# Set job timeout in seconds (default: 600 = 10 min)
homie config --timeout 1800

# View current settings
homie config
```

**Examples:**
- Light usage: `homie config --cpu 1 --memory 2g`
- Medium usage: `homie config --cpu 2 --memory 4g` (default)
- Heavy usage: `homie config --cpu 4 --memory 8g`
- All-in: `homie config --cpu 8 --memory 16g`

After changing settings, restart `homie up` for them to take effect.

### Network Troubleshooting

If peers can't find each other automatically (some routers block UDP broadcast):

```bash
# Manually add a friend by IP address
homie add 192.168.1.42

# Your friend adds you too
homie add 192.168.1.75

# List manually added peers
homie list-direct

# Remove a peer
homie remove 192.168.1.42
```

## Remote Peers (WireGuard Mesh)

Want to connect with friends across the internet, not just your local network? Homie supports a WireGuard mesh network for remote peers.

**Requirements:** Install WireGuard tools first:
```bash
# macOS
brew install wireguard-tools

# Linux
sudo apt install wireguard-tools
```

### Creating a Mesh Network

```bash
# First person creates the network
homie network create my-crew

# Get your public key
homie network join
# Share the displayed public key with your friend
```

### Inviting a Friend

```bash
# You run (paste their public key when prompted)
homie network invite
# Share the invite code with your friend (~60 chars, fits in a text)

# They run
homie network join <invite-code>
```

### Starting with Mesh

```bash
# Start daemon with WireGuard mesh tunnel
homie up --mesh

# You'll be prompted for sudo password (WireGuard needs it)
# Now you can see and run jobs on remote peers!
```

### Mesh Commands

| Command | Description |
|---------|-------------|
| `homie network create <name>` | Create new mesh network |
| `homie network join` | Show public key / join with code |
| `homie network invite` | Generate invite for new peer |
| `homie network status` | Show network and peer info |
| `homie network up` | Bring up tunnel (standalone) |
| `homie network down` | Tear down tunnel |
| `homie network leave` | Leave the mesh network |

See [REMOTE_SETUP.md](REMOTE_SETUP.md) for detailed instructions.

## License

MIT
