# Remote Homie Network Setup

This guide shows how to connect Homie peers across different locations (different houses, cities, countries).

## Two Approaches

| Approach | Status | Dependencies | Best For |
|----------|--------|--------------|----------|
| **Tailscale** | Available now | Tailscale account (free) | Quick setup, works today |
| **Native WireGuard Mesh** | Coming soon | None (fully self-hosted) | No external dependencies |

---

# Option 1: Tailscale (Available Now)

This is the quickest way to get remote Homie working today using Tailscale VPN.

## Why Tailscale?

Homie uses UDP broadcast for peer discovery, which only works on the same local network (WiFi/LAN). To connect peers in different locations, you need a VPN to create a virtual local network.

**Tailscale benefits:**
- ✅ **Zero configuration** - No port forwarding needed
- ✅ **Works behind NAT** - Works from anywhere (coffee shop, office, home)
- ✅ **Encrypted** - WireGuard-based, super secure
- ✅ **Fast** - Direct peer-to-peer connections when possible
- ✅ **Free** - Free for personal use (up to 100 devices)
- ✅ **Cross-platform** - Mac, Windows, Linux

## Step-by-Step Setup

### Step 1: Install Tailscale (Both Machines)

#### On Mac:
```bash
brew install tailscale
```

Or download from: https://tailscale.com/download/mac

#### On Windows:
Download installer from: https://tailscale.com/download/windows

#### On Linux:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

### Step 2: Connect to Tailscale (Both Machines)

#### Start Tailscale:
```bash
# Mac/Linux
sudo tailscale up

# Windows (PowerShell as Admin)
tailscale up
```

This will open a browser window asking you to log in. Both of you should:
1. Sign in with Google/GitHub/Microsoft (use same organization if sharing)
2. Authorize the device

### Step 3: Get Tailscale IPs (Both Machines)

```bash
# Get your Tailscale IP
tailscale ip -4
```

Example outputs:
- **Your machine:** `100.64.1.1`
- **Friend's machine:** `100.64.1.2`

Share these IPs with each other (via text, Discord, etc.)

### Step 4: Add Each Other as Direct Peers

#### On Your Machine:
```bash
# Add your friend's Tailscale IP
homie add 100.64.1.2

# Verify it was added
homie list-direct
```

#### On Friend's Machine:
```bash
# Add your Tailscale IP
homie add 100.64.1.1

# Verify it was added
homie list-direct
```

### Step 5: Start Homie (Both Machines)

```bash
homie up
```

You should see the startup animation and dashboard.

### Step 6: Verify Connection

#### On Your Machine:
```bash
# Check if you can see your friend
homie peers
```

You should see output like:
```
╭─────────────────────── 🏠 HOMIES ON NETWORK ────────────────────────╮
│ NAME     │ IP           │ CPU   │ RAM    │ GPU        │ STATUS     │
├──────────┼──────────────┼───────┼────────┼────────────┼────────────┤
│ bob      │ 100.64.1.2   │ 23% ▓░│ 24.1GB │ RTX 3080   │ ● idle     │
╰──────────┴──────────────┴───────┴────────┴────────────┴────────────╯
```

Notice the IP is the Tailscale IP (100.x.x.x)!

### Step 7: Run Jobs Across the Internet!

```bash
# Run on your remote friend's machine
homie run train.py --env ml-demo

# Run on their GPU
homie run train.py --env ml-demo --gpu

# Run on specific remote peer
homie run train.py --env ml-demo --peer bob
```

## Complete Example Scenario

### Setup: You and Your Friend

**You:** In San Francisco, MacBook Pro, no GPU
**Friend (Bob):** In New York, gaming PC with RTX 3080

### Goal: Use Bob's GPU for ML Training

#### 1. Both Install Tailscale
```bash
# You (Mac)
brew install tailscale
sudo tailscale up

# Bob (Windows)
# Downloads installer, runs it
tailscale up
```

#### 2. Exchange Tailscale IPs
```bash
# You check your IP
tailscale ip -4
# Output: 100.64.1.5

# Bob checks his IP
tailscale ip -4
# Output: 100.64.1.12

# Share via text message
```

#### 3. Add Each Other
```bash
# You add Bob
homie add 100.64.1.12

# Bob adds you
homie add 100.64.1.5
```

#### 4. Start Homie
```bash
# Both run
homie up
```

#### 5. You Run Training on Bob's GPU
```bash
# From San Francisco, using NYC GPU
cd examples/ml-training
homie run train.py --env ml-demo --gpu
```

Output:
```
╭─ Sending to bob (best available) ────────────────────────────────╮
│ Job ID: a1b2c3d4                                                 │
│ Script: train.py                                                 │
╰──────────────────────────────────────────────────────────────────╯

[bob] Training mlp model...
[bob] Iteration 1, loss = 1.04640846
[bob] Iteration 2, loss = 0.90681991
...
[bob] Test accuracy: 0.8875
[bob] ✅ Training completed successfully!

╭─ Job Complete ─────────────────────────────────────────────────╮
│ Runtime: 1.1s                                                  │
│ Downloaded: model.pkl, results.json, training.log             │
╰────────────────────────────────────────────────────────────────╯
```

The model trained in NYC, results downloaded to San Francisco!

#### 6. Check History
```bash
# You can see all remote jobs
homie history

# See jobs run on Bob's machine
homie history --peer bob

# See statistics
homie history --stats
```

## Troubleshooting

### "No peers found"

**Check Tailscale connection:**
```bash
# Verify Tailscale is running
tailscale status

# Should show your friend's machine
```

**Ping each other:**
```bash
# You ping Bob's Tailscale IP
ping 100.64.1.12

# Should get responses
```

**Check Homie direct peers:**
```bash
homie list-direct

# Should show:
# 100.64.1.12
```

### "Connection refused"

**Make sure both are running `homie up`:**
```bash
# Both machines need this running
homie up
```

**Check firewall (Windows):**
- Windows Firewall might block Homie
- Allow Python through firewall when prompted
- Or manually add rule for ports 5555, 5556

### "Job authentication failed"

**Sync clocks:**
```bash
# Mac
sudo sntp -sS time.apple.com

# Windows (PowerShell as Admin)
w32tm /resync

# Linux
sudo timedatectl set-ntp true
```

### "Tailscale IPs don't ping"

**Restart Tailscale:**
```bash
# Mac/Linux
sudo tailscale down
sudo tailscale up

# Windows
# Quit Tailscale from system tray
# Start it again
```

## Security Notes

### ✅ What's Secure

- **Encrypted connection** - All traffic encrypted with WireGuard
- **No public exposure** - Your machines aren't exposed to the internet
- **Authenticated** - Only devices you authorize can join your Tailscale network
- **Group secret** - Homie still uses HMAC authentication with shared secret

### ⚠️ Trust Model

Homie is designed for **trusted friends**. Anyone on your Tailscale network with your Homie group secret can:
- Run code on your machine (in Docker sandbox)
- Use your CPU/RAM/GPU (up to limits you set)

**Only add people you trust!**

### Limiting Resource Usage

```bash
# Control what remote friends can use
homie config --cpu 2      # Max 2 CPU cores
homie config --memory 4g  # Max 4GB RAM
homie config --timeout 600 # Max 10 min per job
```

## Advanced: Multiple Remote Friends

You can have a whole team across different locations:

```bash
# Add all your friends' Tailscale IPs
homie add 100.64.1.5   # Alice in SF
homie add 100.64.1.12  # Bob in NYC
homie add 100.64.1.23  # Charlie in London
homie add 100.64.1.45  # David in Tokyo

# Start Homie
homie up

# See everyone
homie peers
```

Now `homie run` will automatically pick the best available peer globally!

## Comparison: Tailscale vs Port Forwarding

| Feature | Tailscale | Port Forwarding |
|---------|-----------|-----------------|
| Setup time | 5 minutes | 30+ minutes |
| Security | Encrypted (WireGuard) | Exposed to internet |
| NAT traversal | ✅ Works everywhere | ❌ Blocked by many ISPs |
| Mobile/laptop | ✅ Works on any network | ❌ Only works from specific IP |
| Multiple peers | ✅ Easy | ❌ Complex |
| Free | ✅ Yes (personal use) | ✅ Yes |

**Recommendation:** Use Tailscale. It's easier, more secure, and more reliable.

## Quick Reference

```bash
# Install Tailscale
brew install tailscale  # Mac
# or download from tailscale.com

# Connect
sudo tailscale up

# Get your IP
tailscale ip -4

# Add remote friend
homie add 100.64.1.X

# Start Homie
homie up

# Run job on remote peer
homie run script.py --env myenv

# Check connection
homie peers
tailscale status

# Troubleshoot
ping 100.64.1.X
homie list-direct
```

## Need Help?

- **Tailscale docs:** https://tailscale.com/kb/
- **Homie issues:** https://github.com/yourusername/homie-cli/issues
- **Check status:** `tailscale status` and `homie peers`

---

# Option 2: Native WireGuard Mesh (Coming Soon)

> **Status:** Design complete, implementation planned

This is the long-term vision for Homie remote networking - a fully decentralized mesh with no external dependencies.

## Why Native WireGuard?

While Tailscale works great, it requires:
- A Tailscale account (free but external dependency)
- Their coordination servers (single point of failure)
- Trust in their infrastructure

The native WireGuard mesh provides:
- **Zero external dependencies** - Everything runs on your machines
- **Fully decentralized** - No central server or admin required
- **Any peer can invite** - Web of trust model
- **Open source** - WireGuard is built into the Linux kernel

## Architecture: Decentralized Mesh

```
                    HOMIE NETWORK: "my-crew"

    No central admin - every peer is equal
    Anyone can invite anyone else

         ┌─────────┐         ┌─────────┐         ┌─────────┐
         │ Vivek   │◄───────►│  Raj    │◄───────►│ Priya   │
         │(founder)│   P2P   │         │   P2P   │         │
         └─────────┘         └─────────┘         └─────────┘
              ▲                   │                   │
              │                   ▼                   ▼
              │              ┌─────────┐         ┌─────────┐
              └─────────────►│  Alex   │◄───────►│  Sam    │
                      P2P    │(invited │   P2P   │(invited │
                             │ by Raj) │         │by Priya)│
                             └─────────┘         └─────────┘
```

### Design Principles

- **No central server** - Network survives as long as any peer is online
- **Any peer can invite** - Your friends can invite their friends
- **Out-of-band key exchange** - Share keys via text, email, Discord, etc.
- **Gossip protocol** - New peers automatically propagate to everyone
- **End-to-end encrypted** - All traffic encrypted via WireGuard

## How It Will Work

### Creating a Network (First Peer)

```bash
$ homie network create "my-crew"

Creating Homie Network: my-crew

Generating your WireGuard identity...
Done! Network created.

You are the first peer. To add friends:
  homie network invite

Network: my-crew
Your ID: vivek-desktop
Peers: just you (for now)
```

### Inviting Someone (Any Peer Can Do This)

```bash
$ homie network invite

Adding a friend to "my-crew"

1. Ask your friend to run: homie network join
2. They'll give you their public key (44 chars)
3. You'll give them a short invite code

Paste their public key: Yj7KLm2xQ8nH4htodjb60Y7YAfKp9xsVN2rT8m5kLw0=

Name for this peer: raj-laptop

┌─────────────────────────────────────────────────────────────────┐
│ Send this invite code to raj-laptop:                            │
│                                                                 │
│ hm1_bXktY3Jld3xZajdLTG0yfDIwMy4wLjExMy41OjUxODIwfHhLN21ROQ     │
│                                                                 │
│ (fits in a text message!)                                       │
└─────────────────────────────────────────────────────────────────┘

Waiting for raj-laptop to connect...
raj-laptop connected! Sending network bundle...
Done!

Propagating raj-laptop to other peers...
  priya-phone updated
  alex-server updated

raj-laptop is now part of my-crew
```

### Joining a Network (New Peer)

```bash
$ homie network join

Joining a Homie Network

Generating your WireGuard identity...

┌────────────────────────────────────────────────────────────────┐
│ Share this with whoever is inviting you:                       │
│                                                                │
│ Public Key: Yj7KLm2xQ8nH4htodjb60Y7YAfKp9xsVN2rT8m5kLw0=       │
└────────────────────────────────────────────────────────────────┘

Paste the invite code they give you: hm1_bXktY3Jld3xZajd...

Connecting to inviter...
Connected! Receiving network bundle...

Importing network: my-crew
Received 3 peers from raj-laptop
Configuring WireGuard mesh...

Connecting to peers...
  vivek-desktop (direct)
  priya-phone (relay via vivek-desktop)
  alex-server (direct)

You're in!

Run 'homie peers' to see everyone
Run 'homie run script.py' to run jobs on the network
```

### Network Status

```bash
$ homie network status

HOMIE NETWORK: my-crew

You: vivek-desktop

Connected Peers (4):
  NAME             STATUS    CONNECTION    INVITED BY
  raj-laptop       idle      direct        vivek-desktop (you)
  priya-phone      busy      relay         vivek-desktop (you)
  alex-server      idle      direct        raj-laptop
  sam-macbook      offline   -             priya-phone

Network Stats:
  Total compute: 12 CPUs, 48GB RAM, 2 GPUs
  Jobs today: 23 completed, 1 running
```

## Onboarding vs Daily Use

**Important distinction:**

| Phase | Network Requirement |
|-------|---------------------|
| **Onboarding** | Inviter and invitee must be reachable (same LAN, or one has public IP, or via Tailscale for bootstrap) |
| **After joining** | Fully remote from anywhere - works from any network |

Once you've exchanged keys and joined the network, WireGuard handles everything. You can connect from:
- Home WiFi
- Coffee shop
- Airport
- Mobile hotspot
- Work VPN

The WireGuard mesh finds the best path automatically.

## Key Exchange Flow

```
Onboarding: Requires inviter to be online when joiner connects

  Alex (new)                         Raj (existing peer)
      │                                    │
      │  1. Run 'homie network join'       │
      │     Generate WireGuard keypair     │
      │                                    │
      │ ──── public key (via chat) ─────►  │  (short - just the key)
      │                                    │
      │                                    │  2. Run 'homie network invite'
      │                                    │     Generate short invite code
      │                                    │
      │  ◄── invite code (via chat) ────── │  (~50 chars, fits in SMS)
      │                                    │
      │  3. Parse invite code              │
      │     Connect to Raj's endpoint      │
      │                                    │
      │ ◄════ WireGuard tunnel ══════════► │  (point-to-point first)
      │                                    │
      │  ◄── full bundle (over tunnel) ─── │  (encrypted, contains all peers)
      │                                    │
      │  4. Import peers from bundle       │
      │     Configure full mesh            │
      │                                    │
      │  5. Raj announces Alex to network  │
      │                                    │
      │ ◄════════════════════════════════► │  Vivek, Priya, etc.
      │        Direct mesh connectivity    │

After onboarding: Works from anywhere in the world
```

**Key improvement:** Only a short invite code (~50 chars) is shared out-of-band.
The full peer list transfers encrypted over WireGuard, so Alex never sees
network members in plaintext before joining.

## Technical Details

### Short Invite Code (Not Full Bundle)

Instead of sharing a large bundle containing all peers, we use a **short invite code** that only contains connection info for the inviter. The full network details transfer over an encrypted WireGuard tunnel after the initial handshake.

**Why?**
- **Privacy:** Joiner doesn't see all network members until they've authenticated
- **Compact:** ~50-60 characters fits easily in a text message
- **Secure:** Full bundle encrypted over WireGuard, not copy/pasted in plaintext

**Invite code contains only:**
```json
{
  "n": "my-crew",           // network name
  "p": "Yj7KLm2x...",       // inviter's WireGuard public key
  "e": "203.0.113.5:51820", // inviter's endpoint (IP:port)
  "t": "xK7mQ9...",         // one-time auth token
  "a": "10.0.0.4"           // assigned mesh IP for joiner
}
```

Base64 encoded with `hm1_` prefix: `hm1_eyJuIjoibXktY3JldyIsInAiOi...` (~50-60 chars)

**Full bundle (transferred over WireGuard after handshake):**
```json
{
  "version": 1,
  "network_name": "my-crew",
  "group_secret": "encrypted-with-joiner-pubkey",
  "peers": [
    {
      "name": "vivek-desktop",
      "public_key": "...",
      "mesh_ip": "10.0.0.1",
      "endpoints": ["203.0.113.5:51820"]
    },
    {
      "name": "priya-phone",
      "public_key": "...",
      "mesh_ip": "10.0.0.2",
      "endpoints": []
    }
  ],
  "invited_by": "vivek-desktop",
  "signature": "<signed-by-inviter>"
}
```

### Peer Propagation (Gossip Protocol)

When a new peer joins:

1. Inviter creates signed peer announcement
2. Inviter sends announcement to all known peers
3. Each peer adds new peer to their WireGuard config
4. Periodic sync ensures consistency for offline peers

### NAT Traversal

Since there's no central relay, peers help each other:

```
Alex (behind NAT) ──► Vivek (public IP) ──► Sam (behind NAT)
```

As long as at least one peer is publicly reachable, the network stays connected.

### Trust Model

- **Anyone can invite** - Your friends invite their friends
- **Signature chain** - Every peer is signed by their inviter
- **Auditable history** - You can trace who invited whom
- **Same group_secret** - Existing HMAC job auth still works

## CLI Commands (Planned)

```bash
# Network management
homie network create <name>      # Start a new network (you're first peer)
homie network invite             # Invite a new peer
homie network join               # Join an existing network
homie network status             # Show network and peer status
homie network leave              # Leave the network

# Existing commands work over WireGuard
homie peers                      # Shows all network peers
homie run script.py              # Can target any network peer
homie up                         # Listens on WireGuard interface
```

## Comparison: Tailscale vs Native WireGuard Mesh

| Feature | Tailscale | Native WireGuard Mesh |
|---------|-----------|----------------------|
| Setup effort | 5 minutes | 10-15 minutes |
| External dependency | Tailscale account | None |
| Central server | Tailscale's servers | None (fully P2P) |
| NAT traversal | Automatic (their relays) | Via mesh peers |
| Free | Yes (100 devices) | Yes (unlimited) |
| Open source | Client only | Everything |
| Invite model | Account-based | Any peer can invite |
| Works if Tailscale down | No | Yes |

**Recommendation:**
- Use **Tailscale** now - it works today with minimal setup
- Switch to **Native Mesh** when available - for full independence

## Roadmap

1. **Phase 1 (Available):** Tailscale integration with direct peer IPs
2. **Phase 2a:** Core WireGuard key management and bundle format
3. **Phase 2b:** WireGuard interface management
4. **Phase 2c:** Gossip protocol for peer propagation
5. **Phase 2d:** NAT relay through mesh peers

## Files (When Implemented)

```
~/.homie/
├── config.yaml                  # Existing Homie config
├── network/
│   ├── identity.json            # Your WireGuard keypair
│   ├── network.json             # Network metadata
│   └── peers/                   # All known peers
│       ├── vivek-desktop.json
│       ├── raj-laptop.json
│       └── priya-phone.json
└── wireguard/
    └── homie0.conf              # Auto-generated WireGuard config
```

---

## Summary

**Today:** Use Tailscale - it's quick, free, and works great.

**Future:** Native WireGuard mesh will provide full independence with no external services required.

Both approaches maintain the same Homie experience - `homie peers`, `homie run`, etc. work identically. The only difference is how the underlying network connectivity is established.
