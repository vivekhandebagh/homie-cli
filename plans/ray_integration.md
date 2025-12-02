# Ray Integration Plan

## Overview

Enable distributed parallel computing across the homie network using Ray. When a mooch runs `homie run --ray script.py`, homie automatically:
1. Starts a Ray head node on the mooch's machine
2. Instructs all available plugs to join as Ray workers
3. Executes the script (which uses Ray's `@ray.remote` API)
4. Tears down the cluster when the job completes

## Prerequisites

- **WireGuard mesh network**: All homie nodes must be connected via WireGuard with routable IPs (e.g., 10.0.0.0/24). This is developed separately.
- **Ray installed**: Both mooch and all plugs must have Ray installed (`pip install ray`)
- **Docker**: Plugs need Docker for containerized Ray worker execution

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WireGuard Mesh (10.0.0.0/24)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐      "ray-setup"       ┌─────────────────┐            │
│  │     MOOCH       │ ────────────────────►  │     PLUG A      │            │
│  │   10.0.0.1      │                        │    10.0.0.2     │            │
│  │                 │      "ray-setup"       ├─────────────────┤            │
│  │  ┌───────────┐  │ ────────────────────►  │     PLUG B      │            │
│  │  │ Ray Head  │  │                        │    10.0.0.3     │            │
│  │  │ Port 6379 │  │      "ray-setup"       ├─────────────────┤            │
│  │  └───────────┘  │ ────────────────────►  │     PLUG C      │            │
│  │                 │                        │    10.0.0.4     │            │
│  │  Runs train.py  │                        └─────────────────┘            │
│  └─────────────────┘                               │                       │
│          │                                         │                       │
│          │         ┌───────────────────────────────┘                       │
│          │         │                                                       │
│          ▼         ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                     Ray Cluster (ephemeral)                     │       │
│  │                                                                 │       │
│  │   Head: 10.0.0.1:6379                                           │       │
│  │   Workers: 10.0.0.2, 10.0.0.3, 10.0.0.4                         │       │
│  │                                                                 │       │
│  │   @ray.remote tasks distributed across all nodes                │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Design Decisions

### Mooch as Head Node
The mooch (job submitter) always becomes the Ray head node. This avoids head election complexity and makes the cluster lifecycle tied to the job.

### Ephemeral Clusters
Ray clusters exist only for the duration of a single job. No persistent cluster to maintain, no head node stability concerns.

### Container Network Mode
- **Regular jobs** (`homie run script.py`): `network_mode: none` (fully isolated)
- **Ray jobs** (`homie run --ray script.py`): `network_mode: host` (access to WireGuard interface)

Ray requires workers to communicate directly. `network_mode: host` allows containers to bind to the WireGuard interface while maintaining filesystem, process, and resource isolation.

### Ray Runs Inside Containers on Plugs
Plugs run Ray workers inside Docker containers (with `network_mode: host`). This provides:
- Filesystem isolation
- Resource limits (CPU, RAM)
- Process isolation
- Consistent environment

### Mooch Runs Ray Natively
The mooch runs Ray head and the user script natively (not in Docker). This is because:
- Mooch is the one requesting the job (implicit trust in own code)
- Simpler setup for head node
- Direct access to local files

## Protocol Changes

### New Message Types

Add to worker protocol:

| Type | Name | Direction | Purpose |
|------|------|-----------|---------|
| `S` | ray-setup | mooch → plug | Request plug to start Ray worker |
| `T` | ray-teardown | mooch → plug | Request plug to stop Ray worker |

### ray-setup Message

```json
{
  "head_ip": "10.0.0.1",
  "head_port": 6379,
  "job_id": "abc123",
  "ray_version": "2.9.0",
  "auth": {
    "hmac": "...",
    "timestamp": 1234567890
  }
}
```

### ray-setup Response

```json
{
  "success": true,
  "worker_ip": "10.0.0.2",
  "error": null
}
```

### ray-teardown Message

```json
{
  "job_id": "abc123",
  "auth": {
    "hmac": "...",
    "timestamp": 1234567890
  }
}
```

## Implementation Plan

### Phase 1: Detection & Config

**Files:** `homie/utils.py`, `homie/config.py`, `homie/discovery.py`

1. Add Ray detection utility:
```python
# utils.py
def get_ray_info() -> tuple[bool, Optional[str]]:
    """Check if Ray is installed and get version.
    Returns: (is_installed, version)
    """
    try:
        result = subprocess.run(
            ["ray", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse version from output
            version = result.stdout.strip().split()[-1]
            return True, version
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False, None
```

2. Add WireGuard IP detection:
```python
# utils.py
def get_wireguard_ip() -> Optional[str]:
    """Get the WireGuard interface IP if available."""
    try:
        import netifaces
        if 'wg0' in netifaces.interfaces():
            addrs = netifaces.ifaddresses('wg0')
            if netifaces.AF_INET in addrs:
                return addrs[netifaces.AF_INET][0]['addr']
    except ImportError:
        # Fallback: parse ip addr output
        result = subprocess.run(
            ["ip", "addr", "show", "wg0"],
            capture_output=True,
            text=True,
        )
        # Parse inet line...
    return None
```

3. Add to config:
```python
# config.py
@dataclass
class HomieConfig:
    # ... existing fields ...
    ray_port: int = 6379
    ray_dashboard_port: int = 8265
```

4. Extend heartbeat to include Ray capability:
```python
# discovery.py - in _build_heartbeat()
{
    # ... existing fields ...
    "ray_available": True,
    "ray_version": "2.9.0",
    "wireguard_ip": "10.0.0.2",
}
```

5. Extend Peer dataclass:
```python
# discovery.py
@dataclass
class Peer:
    # ... existing fields ...
    ray_available: bool = False
    ray_version: Optional[str] = None
    wireguard_ip: Optional[str] = None
```

### Phase 2: Worker Ray Support

**Files:** `homie/worker.py`, `homie/container.py`

1. Add ray-setup handler to Worker:
```python
# worker.py
def _handle_ray_setup(self, conn: socket.socket) -> None:
    """Handle ray-setup request - start Ray worker in container."""
    # Receive payload
    length_bytes = self._recv_exactly(conn, 4)
    length = int.from_bytes(length_bytes, "big")
    payload = json.loads(self._recv_exactly(conn, length).decode())

    # Verify auth
    if not self._verify_ray_auth(payload):
        self._send_ray_response(conn, False, "Auth failed")
        return

    # Check Ray version compatibility
    local_ray = get_ray_info()
    if not local_ray[0]:
        self._send_ray_response(conn, False, "Ray not installed")
        return
    if local_ray[1] != payload["ray_version"]:
        self._send_ray_response(conn, False, f"Ray version mismatch: {local_ray[1]} vs {payload['ray_version']}")
        return

    # Start Ray worker in container
    try:
        self._start_ray_worker_container(
            head_ip=payload["head_ip"],
            head_port=payload["head_port"],
            job_id=payload["job_id"],
        )
        wg_ip = get_wireguard_ip()
        self._send_ray_response(conn, True, worker_ip=wg_ip)
    except Exception as e:
        self._send_ray_response(conn, False, str(e))
```

2. Add Ray worker container management:
```python
# worker.py
def _start_ray_worker_container(self, head_ip: str, head_port: int, job_id: str) -> None:
    """Start a Ray worker inside a Docker container."""
    import docker
    client = docker.from_env()

    wg_ip = get_wireguard_ip()

    container = client.containers.run(
        image=self.config.ray_worker_image,  # e.g., "homie-ray-worker:latest"
        command=[
            "ray", "start", "--block",
            f"--address={head_ip}:{head_port}",
            f"--node-ip-address={wg_ip}",
        ],
        name=f"homie-ray-{job_id}",
        network_mode="host",  # Required for WireGuard access
        detach=True,
        cpu_period=100000,
        cpu_quota=int(self.config.container_cpu_limit * 100000),
        mem_limit=self.config.container_memory_limit,
        pids_limit=100,
        # No user restriction - Ray needs to manage processes
    )

    self._ray_containers[job_id] = container

def _stop_ray_worker_container(self, job_id: str) -> None:
    """Stop and remove Ray worker container."""
    if job_id in self._ray_containers:
        container = self._ray_containers.pop(job_id)
        try:
            container.stop(timeout=10)
            container.remove()
        except Exception:
            pass
```

3. Add ray-teardown handler:
```python
# worker.py
def _handle_ray_teardown(self, conn: socket.socket) -> None:
    """Handle ray-teardown request - stop Ray worker."""
    length_bytes = self._recv_exactly(conn, 4)
    length = int.from_bytes(length_bytes, "big")
    payload = json.loads(self._recv_exactly(conn, length).decode())

    if not self._verify_ray_auth(payload):
        conn.sendall(b'0')
        return

    self._stop_ray_worker_container(payload["job_id"])
    conn.sendall(b'1')
```

4. Update message type handling:
```python
# worker.py - in _handle_connection()
elif msg_type == b'S':
    self._handle_ray_setup(conn)
elif msg_type == b'T':
    self._handle_ray_teardown(conn)
```

### Phase 3: Client Ray Support

**Files:** `homie/client.py`

1. Add Ray cluster setup method:
```python
# client.py
class Client:
    def setup_ray_cluster(self, peers: list[Peer], job_id: str) -> list[str]:
        """
        Request all peers to join Ray cluster.
        Returns list of worker IPs that successfully joined.
        """
        import ray
        ray_version = ray.__version__
        wg_ip = get_wireguard_ip()

        worker_ips = []
        failed_peers = []

        for peer in peers:
            if not peer.ray_available:
                continue
            if not peer.wireguard_ip:
                continue

            try:
                success, worker_ip = self._send_ray_setup(
                    peer=peer,
                    head_ip=wg_ip,
                    head_port=self.config.ray_port,
                    job_id=job_id,
                    ray_version=ray_version,
                )
                if success:
                    worker_ips.append(worker_ip)
                else:
                    failed_peers.append(peer.name)
            except Exception as e:
                failed_peers.append(peer.name)

        return worker_ips, failed_peers

    def _send_ray_setup(self, peer: Peer, head_ip: str, head_port: int,
                        job_id: str, ray_version: str) -> tuple[bool, Optional[str]]:
        """Send ray-setup message to a peer."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((peer.wireguard_ip, peer.port))

        try:
            # Send message type
            sock.sendall(b'S')

            # Send payload
            payload = {
                "head_ip": head_ip,
                "head_port": head_port,
                "job_id": job_id,
                "ray_version": ray_version,
                "auth": self._build_auth(job_id),
            }
            data = json.dumps(payload).encode()
            sock.sendall(len(data).to_bytes(4, "big"))
            sock.sendall(data)

            # Receive response
            response_data = self._recv_response(sock)
            response = json.loads(response_data)
            return response["success"], response.get("worker_ip")
        finally:
            sock.close()

    def teardown_ray_cluster(self, peers: list[Peer], job_id: str) -> None:
        """Request all peers to leave Ray cluster."""
        for peer in peers:
            try:
                self._send_ray_teardown(peer, job_id)
            except Exception:
                pass  # Best effort

    def _send_ray_teardown(self, peer: Peer, job_id: str) -> None:
        """Send ray-teardown message to a peer."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((peer.wireguard_ip, peer.port))

        try:
            sock.sendall(b'T')
            payload = {
                "job_id": job_id,
                "auth": self._build_auth(job_id),
            }
            data = json.dumps(payload).encode()
            sock.sendall(len(data).to_bytes(4, "big"))
            sock.sendall(data)
            sock.recv(1)  # Ack
        finally:
            sock.close()
```

2. Add Ray job execution:
```python
# client.py
def run_ray_job(
    self,
    script_path: str,
    args: list[str],
    peers: list[Peer],
    on_output: Optional[Callable[[str, str], None]] = None,
) -> int:
    """
    Run a Ray-parallelized job across the homie network.
    Returns exit code.
    """
    import subprocess
    import ray

    job_id = str(uuid.uuid4())[:8]
    wg_ip = get_wireguard_ip()

    if not wg_ip:
        raise RuntimeError("WireGuard interface not found")

    # Step 1: Start Ray head locally
    if on_output:
        on_output("stdout", f"Starting Ray head on {wg_ip}...\n")

    head_process = subprocess.Popen(
        [
            "ray", "start", "--head",
            f"--port={self.config.ray_port}",
            f"--node-ip-address={wg_ip}",
            "--include-dashboard=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    head_process.wait()

    if head_process.returncode != 0:
        raise RuntimeError(f"Failed to start Ray head: {head_process.stderr.read()}")

    try:
        # Step 2: Request peers to join cluster
        if on_output:
            on_output("stdout", f"Setting up cluster with {len(peers)} peers...\n")

        worker_ips, failed = self.setup_ray_cluster(peers, job_id)

        if on_output:
            on_output("stdout", f"Cluster ready: {len(worker_ips)} workers joined\n")
            if failed:
                on_output("stderr", f"Failed to add: {', '.join(failed)}\n")

        # Step 3: Wait for workers to register with Ray
        time.sleep(2)

        # Step 4: Run the script
        if on_output:
            on_output("stdout", f"Running {script_path}...\n")

        env = os.environ.copy()
        env["RAY_ADDRESS"] = f"{wg_ip}:{self.config.ray_port}"

        process = subprocess.Popen(
            ["python", script_path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Stream output
        # ... (similar to existing streaming logic)

        process.wait()
        return process.returncode

    finally:
        # Step 5: Teardown cluster
        if on_output:
            on_output("stdout", "Tearing down Ray cluster...\n")

        self.teardown_ray_cluster(peers, job_id)
        subprocess.run(["ray", "stop"], capture_output=True)
```

### Phase 4: CLI Integration

**Files:** `homie/cli.py`

1. Add `--ray` flag to run command:
```python
# cli.py
@cli.command()
@click.argument("script", type=click.Path(exists=True))
@click.argument("args", nargs=-1)
@click.option("--ray", "use_ray", is_flag=True, help="Run as distributed Ray job")
@click.option("-n", "--name", "peer_name", help="Run on specific peer (ignored with --ray)")
@click.option("--gpu", is_flag=True, help="Require GPU (ignored with --ray)")
@click.option("-f", "--file", "extra_files", multiple=True, help="Additional files to include")
def run(script: str, args: tuple, use_ray: bool, peer_name: str, gpu: bool, extra_files: tuple):
    """Run a script on the homie network."""
    config = HomieConfig.load()

    if use_ray:
        _run_ray_job(config, script, list(args), list(extra_files))
    else:
        _run_single_job(config, script, list(args), peer_name, gpu, list(extra_files))
```

2. Implement Ray job runner:
```python
# cli.py
def _run_ray_job(config: HomieConfig, script: str, args: list[str], extra_files: list[str]):
    """Run a distributed Ray job."""
    from .client import Client
    from .discovery import Discovery
    from .utils import get_ray_info, get_wireguard_ip

    # Check prerequisites
    ray_installed, ray_version = get_ray_info()
    if not ray_installed:
        console.print("[red]Error:[/red] Ray is not installed. Run: pip install ray")
        raise SystemExit(1)

    wg_ip = get_wireguard_ip()
    if not wg_ip:
        console.print("[red]Error:[/red] WireGuard interface not found")
        raise SystemExit(1)

    # Discover peers
    console.print("Discovering peers...")
    discovery = Discovery(config)
    discovery.start(listen=False)
    time.sleep(3)
    discovery.stop()

    peers = discovery.get_peers()
    ray_peers = [p for p in peers if p.ray_available and p.wireguard_ip]

    if not ray_peers:
        console.print("[yellow]Warning:[/yellow] No Ray-capable peers found. Running locally only.")
    else:
        console.print(f"Found {len(ray_peers)} Ray-capable peers")

    # Print cluster info
    table = Table(title="Ray Cluster")
    table.add_column("Node")
    table.add_column("IP")
    table.add_column("Role")
    table.add_row(config.name, wg_ip, "head")
    for p in ray_peers:
        table.add_row(p.name, p.wireguard_ip, "worker")
    console.print(table)

    # Run job
    client = Client(config)

    def on_output(stream: str, data: str):
        if stream == "stdout":
            console.print(data, end="")
        else:
            console.print(f"[red]{data}[/red]", end="")

    try:
        exit_code = client.run_ray_job(
            script_path=script,
            args=args,
            peers=ray_peers,
            on_output=on_output,
        )

        if exit_code == 0:
            console.print("\n[green]✓ Job completed successfully[/green]")
        else:
            console.print(f"\n[red]✗ Job failed with exit code {exit_code}[/red]")

        raise SystemExit(exit_code)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted - tearing down cluster...[/yellow]")
        raise SystemExit(130)
```

### Phase 5: Ray Worker Docker Image

**Files:** `Dockerfile.ray`

Create a base image for Ray workers:

```dockerfile
# Dockerfile.ray
FROM python:3.11-slim

# Install Ray and common dependencies
RUN pip install --no-cache-dir \
    ray[default]==2.9.0 \
    numpy \
    pandas

# Create non-root user
RUN useradd -m -u 1000 homie
USER homie
WORKDIR /home/homie

# Default command - will be overridden
CMD ["ray", "start", "--block"]
```

Build script:
```bash
#!/bin/bash
# build_ray_image.sh
docker build -f Dockerfile.ray -t homie-ray-worker:latest .
```

### Phase 6: Documentation & Examples

**Files:** `examples/ray-parallel/`

1. Create example Ray job:
```python
# examples/ray-parallel/parallel_compute.py
"""
Example: Distributed computation using Ray on homie network.

Usage:
    homie run --ray parallel_compute.py
"""
import ray
import time

# Initialize Ray (connects to existing cluster via RAY_ADDRESS env var)
ray.init()

@ray.remote
def expensive_computation(x: int) -> int:
    """Simulate expensive computation."""
    time.sleep(1)  # Simulate work
    return x * x

def main():
    print(f"Ray cluster resources: {ray.cluster_resources()}")
    print(f"Available nodes: {len(ray.nodes())}")

    # Submit 20 tasks - Ray distributes across all workers
    futures = [expensive_computation.remote(i) for i in range(20)]

    print("Waiting for results...")
    results = ray.get(futures)

    print(f"Results: {results}")
    print(f"Sum: {sum(results)}")

if __name__ == "__main__":
    main()
```

2. Create ML training example:
```python
# examples/ray-parallel/distributed_training.py
"""
Example: Distributed hyperparameter search using Ray Tune.

Usage:
    homie run --ray distributed_training.py
"""
import ray
from ray import tune

ray.init()

def train_model(config):
    """Training function - runs on workers."""
    # Simulate training with hyperparameters
    accuracy = config["lr"] * 10 + config["batch_size"] / 100
    tune.report(accuracy=accuracy)

def main():
    print(f"Starting distributed hyperparameter search...")
    print(f"Cluster resources: {ray.cluster_resources()}")

    analysis = tune.run(
        train_model,
        config={
            "lr": tune.grid_search([0.01, 0.1, 0.5]),
            "batch_size": tune.grid_search([16, 32, 64]),
        },
        resources_per_trial={"cpu": 1},
    )

    print(f"Best config: {analysis.best_config}")

if __name__ == "__main__":
    main()
```

3. Update README:
```markdown
# Ray Parallel Jobs

Run distributed computations across your homie network:

```bash
# Run a Ray-parallelized script
homie run --ray my_parallel_script.py

# Your script uses Ray's @ray.remote decorator
# homie handles cluster setup/teardown automatically
```

## Requirements

- All peers must have Ray installed: `pip install ray`
- All peers must be connected via WireGuard mesh
- Peers advertise Ray capability in heartbeats

## How It Works

1. Your machine becomes the Ray head node
2. All available peers join as Ray workers
3. Your script runs, distributing @ray.remote tasks
4. Cluster tears down when job completes
```

## Testing Plan

### Unit Tests

1. **Ray detection**: Test `get_ray_info()` with/without Ray installed
2. **WireGuard detection**: Test `get_wireguard_ip()` with/without wg0
3. **Message serialization**: Test ray-setup/teardown message format
4. **Auth verification**: Test HMAC validation for Ray messages

### Integration Tests

1. **Single node**: Run Ray job with no peers (head only)
2. **Two nodes**: Run Ray job with one peer
3. **Failure handling**: Peer fails to join, job should continue
4. **Teardown**: Verify containers stop after job
5. **Version mismatch**: Test error when Ray versions differ

### Manual Testing Checklist

- [ ] `homie up` shows Ray capability in peer info
- [ ] `homie peers` displays Ray status for each peer
- [ ] `homie run --ray script.py` sets up cluster
- [ ] Tasks distribute across workers (check Ray dashboard)
- [ ] Cluster tears down after job completes
- [ ] Ctrl+C during job tears down cluster cleanly
- [ ] Works with peers on different subnets via WireGuard

## Security Considerations

### Network Exposure

Ray jobs use `network_mode: host`, which means containers can:
- Access the WireGuard interface (required for Ray)
- Access other network interfaces on the host

**Mitigation**: WireGuard mesh provides the trust boundary. Only authenticated homies can join the mesh.

### Ray Port Exposure

Ray head listens on port 6379. Only accessible via WireGuard IPs.

**Mitigation**: Firewall rules should block Ray ports on public interfaces:
```bash
# Only allow Ray on WireGuard interface
iptables -A INPUT -i wg0 -p tcp --dport 6379 -j ACCEPT
iptables -A INPUT -p tcp --dport 6379 -j DROP
```

### Code Execution

Ray workers execute arbitrary Python code from the head node.

**Mitigation**: Same trust model as regular homie jobs. Only run jobs from trusted peers.

## Future Enhancements

1. **GPU support for Ray**: Pass through GPUs to Ray worker containers
2. **Resource-aware scheduling**: Let homie filter peers by resources before Ray scheduling
3. **Persistent clusters**: Option to keep cluster running between jobs
4. **Ray dashboard access**: Expose dashboard via WireGuard for monitoring
5. **Custom Ray images**: Allow mooches to specify worker image with dependencies
6. **File synchronization**: Sync additional files to workers before job starts
7. **Result collection**: Automatically collect output files from all workers

## Dependencies

New dependencies to add to `setup.py`:

```python
install_requires=[
    # ... existing ...
    "ray>=2.9.0",  # Optional, but required for --ray jobs
]

extras_require={
    "ray": ["ray[default]>=2.9.0"],
}
```

Users can install with: `pip install -e ".[ray]"`
