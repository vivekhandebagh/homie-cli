# 🏠 Join the Homie Network!

Hey! You've been invited to join a peer-to-peer compute network. This lets us share our machines' computing power with each other.

**Time to setup: ~5 minutes**

---

## Step 1: Install Docker

We need Docker to run jobs safely. Install it:

### macOS
```bash
# Option A: Download Docker Desktop
# https://www.docker.com/products/docker-desktop/

# Option B: Use Homebrew
brew install --cask docker
```

Then **open Docker Desktop** and let it start up (you'll see a whale icon in your menu bar).

### Linux (Ubuntu/Debian)
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in, then:
docker run hello-world  # Test it works
```

### Windows
Download Docker Desktop from https://www.docker.com/products/docker-desktop/

---

## Step 2: Get the Code

```bash
# Clone the repo (or download the zip)
git clone <REPO_URL>
cd homie_cli

# Install dependencies
pip install -e .
```

---

## Step 3: Setup Homie

Run the setup wizard:

```bash
homie setup
```

It will ask for:
1. **Your name** - Pick something your friends will recognize (like "raj" or "mike")
2. **Group secret** - Use this: `YOUR_GROUP_SECRET_HERE`

> ⚠️ **Important**: Use the EXACT group secret above. Everyone needs the same secret to connect!

---

## Step 4: Start the Daemon

```bash
homie up
```

You should see:
```
╭──────────────────────────────────────╮
│  🏠 HOMIE COMPUTE                    │
│  Name: your-name                     │
│  IP: 192.168.x.x                     │
│  ...                                 │
╰──────────────────────────────────────╯
  ✓ Docker sandbox ready
  ✓ Discovery broadcasting
  ✓ Worker listening

Waiting for homies...
```

---

## Step 5: Verify It Works

Open another terminal and run:

```bash
homie peers
```

You should see other people who are online:
```
╭────────────────────────────────────────────────────╮
│               🏠 HOMIES ON NETWORK                 │
├──────────┬──────────────┬───────┬────────┬────────┤
│ NAME     │ IP           │ CPU   │ RAM    │ GPU    │
├──────────┼──────────────┼───────┼────────┼────────┤
│ vivek    │ 192.168.1.42 │ 23%   │ 8.2 GB │ -      │
╰──────────┴──────────────┴───────┴────────┴────────╯
```

---

## You're Done! 🎉

### Running a Job

Create a simple test script:
```python
# test.py
print("Hello from a homie's machine!")
import socket
print(f"Running on: {socket.gethostname()}")
```

Then run it on someone else's machine:
```bash
homie run test.py
```

### Run on a Specific Person
```bash
homie run -n vivek test.py
```

### Run with GPU
```bash
homie run --gpu train.py
```

### Include Extra Files
```bash
homie run -f data.csv -f config.json train.py
```

---

## Troubleshooting

### "No homies found on the network"
- Make sure you're on the same WiFi as everyone else
- Check that others have `homie up` running
- Verify you're using the same group secret

### "Docker not available"
- Make sure Docker Desktop is running (look for whale icon)
- Try: `docker run hello-world` to test Docker

### Jobs failing
- The peer needs Docker running too
- Check that the script doesn't need network access (it's disabled for security)

### Can't find each other
- Some corporate/school networks block UDP broadcast
- Try a mobile hotspot as a workaround

---

## Keep It Running

Leave `homie up` running in a terminal while you're on the network. Your idle machine can help your friends run their code!

---

## Commands Reference

| Command | What it does |
|---------|--------------|
| `homie up` | Start sharing your machine |
| `homie peers` | See who's online |
| `homie run script.py` | Run code on a friend's machine |
| `homie run --gpu script.py` | Run on a machine with GPU |
| `homie config` | See your settings |
| `homie whoami` | See your name and IP |

---

Questions? Ask in the group chat!
