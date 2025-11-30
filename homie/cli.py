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
    print_job_complete,
    print_job_error,
    print_job_output,
    print_job_start,
    print_peers_table,
    print_startup_banner,
)
from .utils import get_local_ip
from .worker import Worker


@click.group()
@click.version_option(version=__version__)
def cli():
    """🏠 Homie Compute - P2P distributed compute for friends."""
    pass


@cli.command()
@click.option("--name", "-n", default=None, help="Your display name")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground with live dashboard")
def up(name: str, foreground: bool):
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
        if foreground:
            dashboard.add_event(f"[green]{peer.name}[/] joined ({peer.ip})")

    def on_peer_left(peer: Peer):
        if foreground:
            dashboard.add_event(f"[red]{peer.name}[/] left")

    def on_status_changed(status: str):
        discovery.set_status(status)

    discovery = Discovery(
        config,
        on_peer_joined=on_peer_joined,
        on_peer_left=on_peer_left,
    )

    worker.on_status_changed = on_status_changed

    # Print banner
    print_startup_banner(
        name=config.name,
        ip=ip,
        port=config.worker_port,
        discovery_port=config.discovery_port,
        docker_ok=docker_ok,
        gpu_ok=gpu_ok,
    )

    if not docker_ok:
        console.print("[yellow]Warning:[/] Docker is not available. Jobs will fail to execute.")
        console.print("[dim]Install Docker and try again: https://docs.docker.com/get-docker/[/]")
        console.print()

    # Start services
    discovery.start()
    worker.start()

    console.print("[dim]Waiting for homies... (Ctrl+C to stop)[/]")
    console.print()

    if foreground:
        # Run live dashboard
        dashboard = LiveDashboard(config.name, discovery, worker)
        dashboard.run()
    else:
        # Simple event loop - also write peer cache periodically
        try:
            while True:
                time.sleep(2)
                discovery.write_peer_cache()
        except KeyboardInterrupt:
            pass

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
@click.option("--peer", "-n", default=None, help="Run on specific peer (by name)")
@click.option("--file", "-f", "files", multiple=True, help="Include additional files")
@click.option("--gpu", is_flag=True, help="Request GPU for this job")
@click.option("--wait", "-w", default=3, help="Seconds to wait for peer discovery")
@click.argument("args", nargs=-1)
def run(script: str, peer: str, files: tuple, gpu: bool, wait: int, args: tuple):
    """Run a script on a peer's machine."""
    config = get_or_create_config()

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
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    # Print job start
    print_job_start(target_peer.name, job.job_id, job.filename, job.args)

    # Send job
    client = Client(config)
    result = client.run_job(target_peer, job)

    # Print output
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print_job_output(target_peer.name, line)

    if result.stderr:
        console.print(f"\n[dim]stderr:[/]")
        for line in result.stderr.strip().split("\n"):
            console.print(f"[red]{line}[/]")

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
def ps():
    """List running jobs."""
    console.print("[yellow]Not yet implemented - run 'homie up -f' to see running jobs in the dashboard[/]")


@cli.command()
@click.argument("job_id")
def kill(job_id: str):
    """Kill a running job."""
    console.print("[yellow]Not yet implemented[/]")


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
    console.print(f"  [dim]Container Image:[/]  {cfg.container_image}")
    console.print(f"  [dim]CPU Limit:[/]        {cfg.container_cpu_limit} cores")
    console.print(f"  [dim]Memory Limit:[/]     {cfg.container_memory_limit}")
    console.print(f"  [dim]Timeout:[/]          {cfg.container_timeout}s")
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


if __name__ == "__main__":
    cli()
