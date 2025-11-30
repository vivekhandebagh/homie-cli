# Homie Compute

A peer-to-peer distributed compute system for friends on the same local network.

## The Idea

You and your friends are on the same wifi. Each person has a laptop/desktop with varying specs. Someone has a beefy GPU, someone else has tons of RAM, whatever. When you need to run something heavy, why not use your homies' idle machines?

No cloud, no servers, no accounts. Just a CLI tool and your local network.

---

## How It Works

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

1. Everyone runs `homie up` — starts a daemon
2. Daemons broadcast their existence + stats on the LAN via UDP
3. When you want to run something, your CLI finds available peers
4. Your machine sends code to a peer over TCP
5. Peer executes, streams results back

---

## Core Components

### 1. Discovery Service
**Purpose:** Find other peers on the network

- UDP broadcast on port `5555` (configurable)
- Every 2 seconds, broadcast a heartbeat:
  ```json
  {
    "name": "raj",
    "ip": "192.168.1.42",
    "port": 5556,
    "ram_free_gb": 8.2,
    "cpu_percent_idle": 73,
    "gpu": "rtx3080",
    "gpu_mem_free_gb": 6.1,
    "status": "idle",
    "timestamp": 1701234567
  }
  ```
- Listen for other broadcasts, maintain a peer list
- Peer is "dead" if no heartbeat for 10 seconds

### 2. Worker Daemon
**Purpose:** Receive and execute jobs from peers

- TCP server on port `5556` (configurable)
- Accepts connections from other peers
- Receives a job payload:
  ```json
  {
    "job_id": "abc123",
    "type": "script",
    "filename": "train.py",
    "code": "...base64 encoded...",
    "args": ["--epochs", "10"],
    "files": {
      "data.csv": "...base64 encoded..."
    }
  }
  ```
- Executes in isolated temp directory
- Streams stdout/stderr back over the TCP connection
- Sends back result files when done

### 3. Job Client
**Purpose:** Send jobs to peers

- Connect to peer's TCP port
- Serialize and send the job
- Stream output to local terminal
- Receive result files

### 4. CLI Interface
**Purpose:** Human-friendly commands

```bash
homie up                    # start daemon (discovery + worker)
homie down                  # stop daemon
homie peers                 # list all peers and their resources
homie run script.py         # run on best available peer
homie run -n raj script.py  # run on specific peer
homie run -f data.csv script.py  # include additional files
homie ps                    # list running jobs
homie kill <job_id>         # kill a job
```

### 5. Job Serialization
**Purpose:** Package code and data for transfer

- For simple scripts: just send the .py file
- For projects: tar the directory
- For data: include specified files
- Everything base64 encoded in JSON for simplicity

---

## Directory Structure

```
homie/
├── homie/
│   ├── __init__.py
│   ├── cli.py              # click/argparse CLI entrypoint
│   ├── discovery.py        # UDP broadcast and peer tracking
│   ├── worker.py           # TCP server, job execution
│   ├── client.py           # TCP client, job submission
│   ├── jobs.py             # job serialization/deserialization
│   ├── config.py           # configuration handling
│   └── utils.py            # resource monitoring (ram, cpu, gpu)
├── setup.py
├── requirements.txt
└── README.md
```

---

## Task Breakdown (5 People × 2 Hours)

### Person 1: Discovery (`discovery.py`)
**Time:** ~2 hours

Build the peer discovery system.

**Tasks:**
- [ ] UDP socket setup (broadcast + listen)
- [ ] Heartbeat message format
- [ ] Background thread for broadcasting every 2 seconds
- [ ] Background thread for listening
- [ ] PeerList class that tracks live peers
- [ ] Auto-remove peers after 10s timeout

**Interface:**
```python
class Discovery:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_peers(self) -> list[Peer]: ...
    def get_peer(self, name: str) -> Peer | None: ...
```

**Test it:**
```bash
# terminal 1
python -c "from homie.discovery import Discovery; d = Discovery('alice'); d.start(); input()"

# terminal 2
python -c "from homie.discovery import Discovery; d = Discovery('bob'); d.start(); import time; time.sleep(5); print(d.get_peers())"
```

---

### Person 2: Worker Daemon (`worker.py`)
**Time:** ~2 hours

Build the job execution server.

**Tasks:**
- [ ] TCP server using asyncio or threading
- [ ] Accept incoming connections
- [ ] Receive job payload (JSON)
- [ ] Create temp directory for job
- [ ] Write code/files to temp directory
- [ ] Execute via subprocess
- [ ] Stream stdout/stderr back over socket
- [ ] Send back result files
- [ ] Cleanup temp directory

**Interface:**
```python
class Worker:
    def __init__(self, port: int = 5556): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_running_jobs(self) -> list[Job]: ...
    def kill_job(self, job_id: str) -> bool: ...
```

**Message protocol (simple newline-delimited JSON):**
```
--> {"type": "job", "job_id": "abc", "filename": "test.py", "code": "cHJpbnQoJ2hpJyk=", ...}
<-- {"type": "stdout", "data": "hi\n"}
<-- {"type": "done", "exit_code": 0, "files": {...}}
```

---

### Person 3: Job Client (`client.py`)
**Time:** ~2 hours

Build the client that sends jobs to workers.

**Tasks:**
- [ ] TCP client connection
- [ ] Send job payload
- [ ] Receive and print streamed stdout/stderr
- [ ] Receive result files, write to local disk
- [ ] Handle connection errors gracefully
- [ ] Timeout handling

**Interface:**
```python
class Client:
    def run_job(
        self,
        peer: Peer,
        script_path: str,
        args: list[str] = [],
        files: list[str] = []
    ) -> JobResult: ...
```

---

### Person 4: CLI (`cli.py`)
**Time:** ~2 hours

Build the command-line interface.

**Tasks:**
- [ ] Use `click` or `argparse`
- [ ] `homie up` — start daemon in background (or foreground with flag)
- [ ] `homie down` — stop daemon
- [ ] `homie peers` — pretty print peer list with resources
- [ ] `homie run` — submit a job, stream output
- [ ] `homie ps` — show running jobs
- [ ] `homie kill` — kill a job
- [ ] Config file support (~/.homie/config.yaml)

**Example output:**
```
$ homie peers

NAME     IP              CPU     RAM      GPU          STATUS
────────────────────────────────────────────────────────────
raj      192.168.1.42    73%     8.2 GB   rtx3080      idle
mike     192.168.1.43    12%     16.1 GB  none         idle
sarah    192.168.1.44    91%     2.1 GB   rtx4090      busy

$ homie run train.py --epochs 10

→ sending to raj (best available)
→ job started: abc123

[raj] loading data...
[raj] epoch 1/10 loss=0.45
[raj] epoch 2/10 loss=0.32
...
[raj] done, saved model.pt

→ job complete, downloading results...
→ saved: ./results/model.pt
```

---

### Person 5: Utils + Jobs (`utils.py`, `jobs.py`)
**Time:** ~2 hours

Build resource monitoring and job serialization.

**Tasks for utils.py:**
- [ ] Get free RAM (cross-platform)
- [ ] Get CPU idle percentage
- [ ] Detect GPU (nvidia-smi parsing or pynvml)
- [ ] Get GPU memory free
- [ ] Get hostname

**Tasks for jobs.py:**
- [ ] Job dataclass
- [ ] Serialize job to JSON (base64 encode files)
- [ ] Deserialize JSON to job
- [ ] Package a script file
- [ ] Package a directory (tar + base64)
- [ ] Unpack job to temp directory

**Interface:**
```python
# utils.py
def get_system_stats() -> SystemStats: ...

# jobs.py
@dataclass
class Job:
    job_id: str
    filename: str
    code: bytes
    args: list[str]
    files: dict[str, bytes]

def serialize_job(job: Job) -> str: ...  # JSON string
def deserialize_job(data: str) -> Job: ...
def package_script(path: str, extra_files: list[str] = []) -> Job: ...
```

---

## Integration Plan

**Hour 1:** Everyone builds their component independently

**Hour 1.5:** Start integrating
- Person 1 + 2: Discovery + Worker daemon combined
- Person 3 + 4: Client + CLI combined
- Person 5: Provides utils to everyone

**Hour 2:** Full integration + testing
- Wire everything together
- Test with real jobs across machines
- Fix bugs

---

## Dependencies

```
# requirements.txt
click>=8.0
psutil>=5.9
pynvml>=11.0  # optional, for nvidia gpu detection
```

---

## Stretch Goals (If Time Permits)

- [ ] **Job queue** — if peer is busy, queue the job
- [ ] **Karma system** — track compute contributed vs consumed
- [ ] **File sync** — only send files that changed
- [ ] **Scatter jobs** — split data across multiple peers
- [ ] **GPU selection** — `homie run --gpu train.py`
- [ ] **Live stats** — `homie top` shows real-time cluster usage
- [ ] **Job resume** — checkpoint and resume if connection drops

---

## Security Considerations

This is a **trusted friends** system. There's no auth, no sandboxing. Anyone on your network could:
- See your broadcasts
- Connect to your worker
- Execute arbitrary code on your machine

**Only run this on networks you trust with people you trust.**

Future improvements could add:
- Pre-shared key authentication
- Code signing
- Container/sandbox execution

---

## Example Session

```bash
# raj's machine
$ homie up
daemon started, broadcasting as "raj"
listening for jobs on :5556

# mike's machine  
$ homie up
daemon started, broadcasting as "mike"
listening for jobs on :5556

# your machine
$ homie up
daemon started, broadcasting as "you"
listening for jobs on :5556

$ homie peers
raj   192.168.1.42  idle   8GB   rtx3080
mike  192.168.1.43  idle   16GB  none

$ homie run train.py
→ running on raj
[raj] training started...
[raj] epoch 1 done
[raj] epoch 2 done
[raj] saved model.pt
→ done, fetched model.pt

$ ls
train.py  model.pt
```

---

## Let's Build It

Everyone clone the repo, pick your component, and let's get it done. Sync up at the hour mark to start integrating.

Questions? Ping in the group chat. Ship it. 🚀
