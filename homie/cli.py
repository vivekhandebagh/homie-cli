"""CLI interface for Homie Compute."""

import os
import sys
import time
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .client import Client
from .config import get_or_create_config, save_config, HomieConfig
from .discovery import Discovery, Peer
from .jobs import create_job
from .ui import (
    LiveDashboard,
    console,
    create_history_table,
    print_history_summary,
    print_job_complete,
    print_job_error,
    print_job_output,
    print_job_start,
    print_peers_table,
)
from .utils import get_local_ip
from .worker import Worker


@click.group()
@click.version_option(version=__version__)
def cli():
    """🏠 Homie Compute - P2P distributed compute for friends."""
    pass


# ============================================================================
# Environment Management Commands
# ============================================================================

@cli.group()
def env():
    """Manage execution environments (Docker images)."""
    pass


@env.command("create")
@click.argument("name")
@click.argument("image")
def env_create(name: str, image: str):
    """Create a named environment.

    Example: homie env create ml pytorch/pytorch:latest
    """
    config = get_or_create_config()
    config.envs[name] = image
    save_config(config)
    console.print(f"[green]✓[/] Created env '[cyan]{name}[/]' → {image}")


@env.command("list")
def env_list():
    """List all environments."""
    config = get_or_create_config()
    if not config.envs:
        console.print("[dim]No environments configured[/]")
        console.print("Create one with: [bold]homie env create <name> <image>[/]")
        return

    console.print("[bold]Environments:[/]")
    for name, image in config.envs.items():
        default_marker = " [dim](default)[/]" if name == config.default_env else ""
        console.print(f"  [cyan]{name}[/]: {image}{default_marker}")


@env.command("default")
@click.argument("name")
def env_default(name: str):
    """Set the default environment."""
    config = get_or_create_config()
    if name not in config.envs:
        console.print(f"[red]Env '{name}' not found[/]")
        console.print("Available envs:", ", ".join(config.envs.keys()) or "(none)")
        sys.exit(1)
    config.default_env = name
    save_config(config)
    console.print(f"[green]✓[/] Default env set to '[cyan]{name}[/]'")


@env.command("remove")
@click.argument("name")
def env_remove(name: str):
    """Remove an environment."""
    config = get_or_create_config()
    if name not in config.envs:
        console.print(f"[yellow]Env '{name}' not found[/]")
        return
    if name == config.default_env:
        console.print(f"[yellow]Warning:[/] Removing default env. Set a new default with 'homie env default <name>'")
    del config.envs[name]
    save_config(config)
    console.print(f"[green]✓[/] Removed env '[cyan]{name}[/]'")


# ============================================================================
# Main Commands
# ============================================================================

@cli.command()
@click.option("--name", "-n", default=None, help="Your display name")
def up(name: str):
    """Start the Homie daemon (discovery + worker)."""
    config = get_or_create_config()

    if name:
        config.name = name
        save_config(config)

    ip = get_local_ip()

    # Create worker
    worker = Worker(config)

    # Check Docker availability
    docker_ok = worker.is_docker_available()
    gpu_ok = worker.has_gpu_support() if docker_ok else False

    # Create discovery with callbacks
    def on_peer_joined(peer: Peer):
        dashboard.add_event(f"[green]{peer.name}[/] joined ({peer.ip})")

    def on_peer_left(peer: Peer):
        dashboard.add_event(f"[red]{peer.name}[/] left")

    def on_status_changed(status: str):
        discovery.set_status(status)

    discovery = Discovery(
        config,
        on_peer_joined=on_peer_joined,
        on_peer_left=on_peer_left,
    )

    worker.on_status_changed = on_status_changed

    # Start services
    discovery.start()
    worker.start()

    # Run live dashboard
    dashboard = LiveDashboard(config.name, discovery, worker, docker_ok, gpu_ok)
    dashboard.run()

    # Cleanup
    console.print("\n[dim]Shutting down...[/]")
    discovery.stop()
    worker.stop()


@cli.command()
def down():
    """Stop the Homie daemon."""
    # For now, just print instructions since we're not daemonizing
    console.print("[yellow]Use Ctrl+C to stop the daemon running in another terminal.[/]")


@cli.command()
@click.option("--wait", "-w", default=3, help="Seconds to wait for discovery")
def peers(wait: int):
    """List all peers on the network."""
    config = get_or_create_config()

    # First, try to read from the peer cache file (written by homie up)
    peer_cache = Path.home() / ".homie" / "peer_cache.json"
    if peer_cache.exists():
        import json
        try:
            cache_data = json.loads(peer_cache.read_text())
            cache_age = time.time() - cache_data.get("timestamp", 0)
            if cache_age < 10:  # Cache is fresh (less than 10 seconds old)
                peer_list = [
                    Peer(
                        name=p["name"],
                        ip=p["ip"],
                        port=p["port"],
                        cpu_percent_used=p["cpu_percent_used"],
                        ram_free_gb=p["ram_free_gb"],
                        ram_total_gb=p["ram_total_gb"],
                        gpu_name=p.get("gpu_name"),
                        gpu_memory_free_gb=p.get("gpu_memory_free_gb"),
                        status=p["status"],
                        last_seen=p.get("last_seen", time.time()),
                    )
                    for p in cache_data.get("peers", [])
                ]
                console.print()
                print_peers_table(peer_list)
                return
        except Exception:
            pass

    # Fallback: do our own discovery (works if homie up isn't running)
    console.print(f"[dim]Discovering peers for {wait} seconds...[/]")
    console.print(f"[dim](For faster results, run 'homie up' in another terminal)[/]")

    discovery = Discovery(config)
    discovery.start(listen=False)

    time.sleep(wait)

    peer_list = discovery.get_peers()
    discovery.stop()

    console.print()
    print_peers_table(peer_list)


def _get_peers_from_cache(config) -> list:
    """Try to get peers from cache file."""
    import json
    peer_cache = Path.home() / ".homie" / "peer_cache.json"
    if peer_cache.exists():
        try:
            cache_data = json.loads(peer_cache.read_text())
            cache_age = time.time() - cache_data.get("timestamp", 0)
            if cache_age < 10:  # Cache is fresh
                return [
                    Peer(
                        name=p["name"],
                        ip=p["ip"],
                        port=p["port"],
                        cpu_percent_used=p["cpu_percent_used"],
                        ram_free_gb=p["ram_free_gb"],
                        ram_total_gb=p["ram_total_gb"],
                        gpu_name=p.get("gpu_name"),
                        gpu_memory_free_gb=p.get("gpu_memory_free_gb"),
                        status=p["status"],
                        last_seen=p.get("last_seen", time.time()),
                    )
                    for p in cache_data.get("peers", [])
                ]
        except Exception:
            pass
    return None


@cli.command()
@click.argument("script", type=click.Path(exists=True))
@click.option("--peer", "-p", default=None, help="Run on specific peer (by name)")
@click.option("--env", "-e", "env_name", default=None, help="Use named environment")
@click.option("--image", "-i", default=None, help="Use specific Docker image (overrides --env)")
@click.option("--file", "-f", "files", multiple=True, help="Include additional files")
@click.option("--gpu", is_flag=True, help="Request GPU for this job")
@click.option("--wait", "-w", default=3, help="Seconds to wait for peer discovery")
@click.argument("args", nargs=-1)
def run(script: str, peer: str, env_name: str, image: str, files: tuple, gpu: bool, wait: int, args: tuple):
    """Run a script on a peer's machine.

    Examples:
        homie run train.py                    # Uses default env
        homie run train.py --env ml           # Uses 'ml' env
        homie run train.py --image python:3.9 # Uses specific image
    """
    config = get_or_create_config()

    # Resolve image: --image > --env > default_env
    if image:
        resolved_image = image
    elif env_name:
        if env_name not in config.envs:
            console.print(f"[red]Env '{env_name}' not found[/]")
            console.print("Available envs:", ", ".join(config.envs.keys()) or "(none)")
            console.print("Create one with: [bold]homie env create <name> <image>[/]")
            sys.exit(1)
        resolved_image = config.envs[env_name]
    else:
        resolved_image = config.envs.get(config.default_env, "python:3.11-slim")

    # First try to get peers from cache (if homie up is running)
    cached_peers = _get_peers_from_cache(config)

    if cached_peers:
        console.print(f"[dim]Using peers from running daemon...[/]")
        peer_list = cached_peers
    else:
        # Fallback: do our own discovery
        console.print(f"[dim]Discovering peers for {wait} seconds...[/]")
        console.print(f"[dim](For faster results, run 'homie up' in another terminal)[/]")

        discovery = Discovery(config)
        discovery.start(listen=False)
        time.sleep(wait)
        peer_list = discovery.get_peers()
        discovery.stop()

    # Select peer
    if peer:
        # Find peer by name
        target_peer = next((p for p in peer_list if p.name == peer), None)
        if not target_peer:
            console.print(f"[red]Peer '{peer}' not found[/]")
            sys.exit(1)
    else:
        # Find best available peer
        available = [
            p for p in peer_list
            if p.status == "idle" and (not gpu or p.gpu_name)
        ]
        if not available:
            console.print("[red]No available peers found[/]")
            if gpu:
                console.print("[dim]Try without --gpu flag, or wait for a peer with GPU[/]")
            sys.exit(1)

        # Score and pick best
        def score(p):
            ram_score = p.ram_free_gb
            cpu_score = (100 - p.cpu_percent_used) / 100
            gpu_bonus = 2.0 if p.gpu_name and gpu else 0
            return ram_score * cpu_score + gpu_bonus

        target_peer = max(available, key=score)

    # Create job
    try:
        job = create_job(
            sender=config.name,
            script_path=script,
            args=list(args),
            extra_files=list(files),
            require_gpu=gpu,
            image=resolved_image,
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    # Print job start
    print_job_start(target_peer.name, job.job_id, job.filename, job.args)

    # Streaming output callbacks
    def on_stdout(data: str):
        # Print each chunk as it arrives (handle partial lines)
        for line in data.splitlines(keepends=True):
            if line.endswith('\n'):
                print_job_output(target_peer.name, line.rstrip('\n'))
            else:
                # Partial line - print without newline prefix
                console.print(f"[dim][{target_peer.name}][/] {line}", end="")

    def on_stderr(data: str):
        for line in data.splitlines(keepends=True):
            console.print(f"[red]{line.rstrip()}")

    # Send job with streaming output
    client = Client(config)
    result = client.run_job(
        target_peer,
        job,
        on_stdout=on_stdout,
        on_stderr=on_stderr,
    )

    # Note: stdout/stderr already printed via streaming, but final result may have more
    # (e.g., if connection was lost mid-stream)

    # Save output files
    output_files = []
    for filename, content in result.output_files.items():
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        output_files.append(filename)

    # Print result
    if result.error:
        print_job_error(result.error)
        sys.exit(1)
    elif result.exit_code != 0:
        print_job_error(f"Exit code: {result.exit_code}")
        sys.exit(result.exit_code)
    else:
        print_job_complete(result.runtime_seconds, output_files)


@cli.command()
@click.option("--peer", "-p", default=None, help="Query specific peer (by name)")
@click.option("--wait", "-w", default=3, help="Seconds to wait for peer discovery")
def ps(peer: str, wait: int):
    """List running jobs on peers."""
    config = get_or_create_config()

    # Get peers from cache or discover
    cached_peers = _get_peers_from_cache(config)

    if cached_peers:
        peer_list = cached_peers
    else:
        console.print(f"[dim]Discovering peers for {wait} seconds...[/]")
        discovery = Discovery(config)
        discovery.start(listen=False)
        time.sleep(wait)
        peer_list = discovery.get_peers()
        discovery.stop()

    if not peer_list:
        console.print("[yellow]No peers found[/]")
        return

    # Filter to specific peer if requested
    if peer:
        peer_list = [p for p in peer_list if p.name == peer]
        if not peer_list:
            console.print(f"[red]Peer '{peer}' not found[/]")
            return

    # Query each peer for running jobs
    client = Client(config)
    total_jobs = 0

    for p in peer_list:
        jobs = client.list_jobs(p)
        if jobs is None:
            console.print(f"[dim]{p.name}:[/] [red]connection failed[/]")
            continue
        if not jobs:
            console.print(f"[dim]{p.name}:[/] no jobs running")
            continue

        console.print(f"[bold]{p.name}[/]:")
        for job in jobs:
            job_id = job.get("job_id", "?")
            sender = job.get("sender", "?")
            filename = job.get("filename", "?")
            start_time = job.get("start_time", 0)
            elapsed = time.time() - start_time if start_time else 0
            elapsed_str = f"{int(elapsed)}s" if elapsed < 60 else f"{int(elapsed/60)}m{int(elapsed%60)}s"
            console.print(f"  [cyan]{job_id}[/]  {filename}  from [green]{sender}[/]  ({elapsed_str})")
            total_jobs += 1

    if total_jobs == 0:
        console.print("\n[dim]No jobs currently running on any peer[/]")


@cli.command()
@click.argument("job_id")
@click.option("--local", "-l", is_flag=True, help="Kill job running locally (as plug)")
@click.option("--peer", "-p", default=None, help="Kill on specific peer (by name)")
@click.option("--wait", "-w", default=3, help="Seconds to wait for peer discovery")
def kill(job_id: str, local: bool, peer: str, wait: int):
    """Kill a running job by ID.

    As a mooch: kills jobs you sent to peers.
    As a plug (--local): kills any job running on your machine.
    """
    config = get_or_create_config()

    # Local kill - plug killing job on their own machine
    if local:
        from .container import ContainerExecutor
        executor = ContainerExecutor()
        if executor.kill_job(job_id):
            console.print(f"[green]✓[/] Killed local job [cyan]{job_id}[/]")
        else:
            console.print(f"[yellow]Job {job_id} not found locally[/]")
        return

    # Remote kill - mooch killing their own job on a peer
    cached_peers = _get_peers_from_cache(config)

    if cached_peers:
        peer_list = cached_peers
    else:
        console.print(f"[dim]Discovering peers for {wait} seconds...[/]")
        discovery = Discovery(config)
        discovery.start(listen=False)
        time.sleep(wait)
        peer_list = discovery.get_peers()
        discovery.stop()

    if not peer_list:
        console.print("[yellow]No peers found[/]")
        return

    client = Client(config)

    # If peer specified, only try that one
    if peer:
        target_peers = [p for p in peer_list if p.name == peer]
        if not target_peers:
            console.print(f"[red]Peer '{peer}' not found[/]")
            return
    else:
        target_peers = peer_list

    # Try to kill on each peer
    killed = False
    for p in target_peers:
        success = client.kill_job(p, job_id)
        if success:
            console.print(f"[green]✓[/] Killed job [cyan]{job_id}[/] on {p.name}")
            killed = True
            break

    if not killed:
        console.print(f"[yellow]Job {job_id} not found, not authorized, or already completed[/]")


@cli.command()
@click.option("--cpu", type=float, help="Set CPU core limit (e.g., 2.0)")
@click.option("--memory", type=str, help="Set memory limit (e.g., 4g, 8g)")
@click.option("--timeout", type=int, help="Set job timeout in seconds")
def config(cpu: float, memory: str, timeout: int):
    """Show or update configuration."""
    cfg = get_or_create_config()

    # Update config if options provided
    changed = False
    if cpu is not None:
        cfg.container_cpu_limit = cpu
        changed = True
        console.print(f"[green]✓[/] CPU limit set to {cpu} cores")
    if memory is not None:
        cfg.container_memory_limit = memory
        changed = True
        console.print(f"[green]✓[/] Memory limit set to {memory}")
    if timeout is not None:
        cfg.container_timeout = timeout
        changed = True
        console.print(f"[green]✓[/] Timeout set to {timeout}s")

    if changed:
        save_config(cfg)
        console.print()
        console.print("[dim]Restart 'homie up' for changes to take effect[/]")
        console.print()

    console.print("[bold]Current Configuration[/]")
    console.print()
    console.print(f"  [dim]Name:[/]           {cfg.name}")
    console.print(f"  [dim]Discovery Port:[/] {cfg.discovery_port}")
    console.print(f"  [dim]Worker Port:[/]    {cfg.worker_port}")
    console.print(f"  [dim]Group Secret:[/]   {cfg.group_secret[:8]}...")
    console.print()
    console.print(f"  [dim]CPU Limit:[/]        {cfg.container_cpu_limit} cores")
    console.print(f"  [dim]Memory Limit:[/]     {cfg.container_memory_limit}")
    console.print(f"  [dim]Timeout:[/]          {cfg.container_timeout}s")
    console.print()
    console.print(f"  [dim]Default Env:[/]      {cfg.default_env} ({cfg.envs.get(cfg.default_env, 'not set')})")
    console.print(f"  [dim]Environments:[/]     {len(cfg.envs)} configured")
    console.print()
    console.print(f"[dim]Config file: ~/.homie/config.yaml[/]")


@cli.command()
@click.option("--name", prompt="Your display name", default=lambda: os.environ.get("USER", "homie"))
@click.option("--secret", prompt="Group secret (share with your homies)", default=None)
def setup(name: str, secret: str):
    """Interactive setup wizard."""
    from .container import ContainerExecutor

    console.print()
    console.print("[bold blue]🏠 Homie Compute Setup[/]")
    console.print()

    # Check Docker
    console.print("Checking Docker... ", end="")
    executor = ContainerExecutor()
    if executor.is_available():
        console.print("[green]OK[/]")
    else:
        console.print("[red]NOT FOUND[/]")
        console.print("[yellow]Please install Docker: https://docs.docker.com/get-docker/[/]")
        console.print()

    # Check GPU
    console.print("Checking GPU support... ", end="")
    if executor.is_available() and executor.has_gpu_support():
        console.print("[green]OK[/]")
    else:
        console.print("[dim]not available[/]")

    # Create config
    config = HomieConfig(name=name)
    if secret:
        config.group_secret = secret

    save_config(config)

    console.print()
    console.print("[green]✓[/] Configuration saved to ~/.homie/config.yaml")
    console.print()
    console.print("[bold]Share this with your homies:[/]")
    console.print(f"  Group Secret: [cyan]{config.group_secret}[/]")
    console.print()
    console.print("Run [bold]homie up[/] to start the daemon!")


@cli.command()
def whoami():
    """Show your identity."""
    config = get_or_create_config()
    ip = get_local_ip()

    console.print(f"[bold]Name:[/]   {config.name}")
    console.print(f"[bold]IP:[/]     {ip}")
    console.print(f"[bold]Ports:[/]  {config.discovery_port} (discovery), {config.worker_port} (worker)")


@cli.command()
@click.argument("ip")
def add(ip: str):
    """Add a peer by IP address (for networks that block broadcast)."""
    from pathlib import Path

    # Validate IP format (basic check)
    parts = ip.split(".")
    if len(parts) != 4:
        console.print(f"[red]Invalid IP address: {ip}[/]")
        sys.exit(1)

    peers_file = Path.home() / ".homie" / "peers"
    peers_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing peers
    existing = []
    if peers_file.exists():
        existing = [p.strip() for p in peers_file.read_text().split("\n") if p.strip()]

    if ip in existing:
        console.print(f"[yellow]Peer {ip} already added[/]")
    else:
        existing.append(ip)
        peers_file.write_text("\n".join(existing) + "\n")
        console.print(f"[green]✓[/] Added peer: {ip}")
        console.print()
        console.print("[dim]This peer will now receive direct heartbeats.[/]")
        console.print("[dim]Make sure they also run: homie add YOUR_IP[/]")


@cli.command()
@click.argument("ip")
def remove(ip: str):
    """Remove a direct peer by IP address."""
    from pathlib import Path

    peers_file = Path.home() / ".homie" / "peers"

    if not peers_file.exists():
        console.print(f"[yellow]No direct peers configured[/]")
        return

    existing = [p.strip() for p in peers_file.read_text().split("\n") if p.strip()]

    if ip in existing:
        existing.remove(ip)
        if existing:
            peers_file.write_text("\n".join(existing) + "\n")
        else:
            peers_file.unlink()
        console.print(f"[green]✓[/] Removed peer: {ip}")
    else:
        console.print(f"[yellow]Peer {ip} not in list[/]")


@cli.command("list-direct")
def list_direct():
    """List manually added peer IPs."""
    from pathlib import Path

    peers_file = Path.home() / ".homie" / "peers"

    if not peers_file.exists():
        console.print("[dim]No direct peers configured[/]")
        console.print()
        console.print("Add a peer with: [bold]homie add <IP>[/]")
        return

    existing = [p.strip() for p in peers_file.read_text().split("\n") if p.strip()]

    if not existing:
        console.print("[dim]No direct peers configured[/]")
        return

    console.print("[bold]Direct peers (bypass broadcast):[/]")
    for ip in existing:
        console.print(f"  {ip}")


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of jobs to show (default: 20)")
@click.option("--peer", "-p", default=None, help="Filter by peer name")
@click.option("--role", "-r", type=click.Choice(["mooch", "plug"]), help="Filter by role (mooch=sent, plug=ran)")
@click.option("--failed", is_flag=True, help="Show only failed jobs")
@click.option("--success", is_flag=True, help="Show only successful jobs")
@click.option("--since", "-s", default=None, help="Show jobs since (e.g., '1d', '12h', '30m')")
@click.option("--stats", is_flag=True, help="Show summary statistics")
@click.option("--clear", is_flag=True, help="Clear all history")
def history(limit: int, peer: str, role: str, failed: bool, success: bool, since: str, stats: bool, clear: bool):
    """Show job history.

    Examples:
        homie history                    # Show last 20 jobs
        homie history -n 50              # Show last 50 jobs
        homie history --peer raj         # Jobs involving peer 'raj'
        homie history --role mooch       # Jobs you sent to others
        homie history --role plug        # Jobs others ran on your machine
        homie history --failed           # Only failed jobs
        homie history --since 1d         # Jobs from last day
        homie history --stats            # Show summary statistics
        homie history --clear            # Clear all history
    """
    from .history import clear_history, get_history_stats, read_history
    from rich.panel import Panel

    # Handle clear
    if clear:
        count = clear_history()
        console.print(f"[green]✓[/] Cleared {count} job(s) from history")
        return

    # Parse since parameter
    since_timestamp = None
    if since:
        import re
        match = re.match(r"(\d+)([dhm])", since)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == "d":
                since_timestamp = time.time() - (value * 86400)
            elif unit == "h":
                since_timestamp = time.time() - (value * 3600)
            elif unit == "m":
                since_timestamp = time.time() - (value * 60)
        else:
            console.print(f"[red]Invalid --since format. Use: 1d, 12h, 30m[/]")
            return

    # Get statistics
    history_stats = get_history_stats()

    # Show stats if requested
    if stats or history_stats["total_jobs"] == 0:
        print_history_summary(history_stats)
        if history_stats["total_jobs"] == 0:
            console.print("[dim]No jobs in history yet[/]")
            console.print("[dim]Run 'homie run <script>' to execute jobs[/]")
            return
        if stats:
            # If --stats flag, just show stats and exit
            return

    # Read history with filters
    entries = read_history(
        limit=limit,
        role=role,
        peer=peer,
        success_only=success,
        failed_only=failed,
        since=since_timestamp,
    )

    if not entries:
        console.print("[yellow]No jobs found matching filters[/]")
        return

    # Build title with active filters
    title_parts = ["JOB HISTORY"]
    if peer:
        title_parts.append(f"peer={peer}")
    if role:
        title_parts.append(f"role={role}")
    if failed:
        title_parts.append("failed only")
    elif success:
        title_parts.append("success only")
    if since:
        title_parts.append(f"since {since}")

    title = " │ ".join(title_parts)

    # Display history table
    console.print()
    console.print(
        Panel(
            create_history_table(entries, show_role=(role is None)),
            title=f"[bold]{title}[/]",
            subtitle=f"[dim]Showing {len(entries)} of {history_stats['total_jobs']} total jobs[/]",
            border_style="cyan",
        )
    )
    console.print()

    # Show legend
    console.print("[dim]Legend:[/] [cyan]→[/] mooch (sent) │ [green]←[/] plug (ran) │ [yellow]⚡[/] GPU")


if __name__ == "__main__":
    cli()
