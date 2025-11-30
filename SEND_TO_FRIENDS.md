# Copy-paste this message to your friends:

---

## 🏠 Join My Compute Network!

Hey! I set up a P2P compute sharing thing. We can run code on each other's machines when we need more power.

### Setup (5 min):

**1. Make sure Docker is running**
   - Download: https://docker.com/products/docker-desktop
   - Open it and wait for the whale icon

**2. Install Homie:**
```bash
git clone https://github.com/YOUR_USERNAME/homie_cli.git
cd homie_cli
pip install -e .
```

**3. Configure with our group secret:**
```bash
homie setup
```
- Enter your name (something I'll recognize)
- For group secret, use: `JXb_93AK00fHAbeCpC5Tyg`

**4. Start sharing:**
```bash
homie up
```

### That's it!

Once you're running `homie up`, I'll be able to see you with `homie peers` and we can run code on each other's machines.

**Quick test:**
```bash
# See who's online
homie peers

# Run a test script on someone's machine
echo "print('Hello from a homie!')" > test.py
homie run test.py
```

Leave `homie up` running while you're on the network!

---

# For yourself (don't send this part):

Your group secret is: `JXb_93AK00fHAbeCpC5Tyg`

To start your daemon:
```bash
homie up
```

To see connected peers:
```bash
homie peers
```
