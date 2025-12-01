# Remote Homie Network Setup with Tailscale

This guide shows how to connect Homie peers across different locations (different houses, cities, countries) using Tailscale VPN.

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
