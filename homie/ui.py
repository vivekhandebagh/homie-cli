"""Beautiful terminal UI using rich."""

import time
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from .discovery import Discovery, Peer
from .utils import get_local_ip, get_system_stats
from .worker import Worker


console = Console()


# ASCII art frames for startup animation
HOMIE_LOGO = r"""
    __  ______  __  _____________
   / / / / __ \/  |/  /  _/ ____/
  / /_/ / / / / /|_/ // // __/
 / __  / /_/ / /  / // // /___
/_/ /_/\____/_/  /_/___/_____/
"""

POWERUP_FRAMES = [
    # Frame 1 - Empty
    r"""
        .  *  .     .   *   .
    .      .    .        .
      *  .    .   *   .    *
    .    .  *     .    .
        .      .    *    .
    """,
    # Frame 2 - Dots appearing
    r"""
        .  *  .  o  .   *   .
    .   o  .    .    o   .
      *  .  o .   *   . o  *
    .  o .  *     . o  .
        .   o  .    *  o .
    """,
    # Frame 3 - Lines connecting
    r"""
        o──*──o  o──*───o
    o─────o────o────o───o
      *──o──o────*───o──*
    o──o──*─────o──o──o
        o───o──o────*──o
    """,
    # Frame 4 - Network forming
    r"""
       ╭──o──╮  ╭──o──╮
    ╭──o──╮──╰──o──╯──╭──o
    │  ╰──o────╮──o───╯  │
    ╰──o──╯────╰──o──╮───╯
       ╰──o──────o──╯
    """,
    # Frame 5 - Network active
    r"""
       ╭──●──╮  ╭──●──╮
    ╭──●──╮──╰══●══╯──╭──●
    │  ╰══●════╮══●═══╯  │
    ╰══●══╯════╰══●══╮═══╯
       ╰══●══════●══╯
    """,
]

CONNECT_MESSAGES = [
    "Initializing...",
    "Scanning network...",
    "Establishing connections...",
    "Joining mesh...",
    "ONLINE",
]


def play_startup_animation(name: str) -> None:
    """Play the startup animation sequence."""
    # Clear and show logo
    console.clear()

    # Show logo with fade-in effect
    logo_lines = HOMIE_LOGO.strip().split('\n')
    for i in range(len(logo_lines) + 1):
        console.clear()
        partial_logo = '\n'.join(logo_lines[:i])
        console.print(f"[bold cyan]{partial_logo}[/]")
        time.sleep(0.08)

    time.sleep(0.3)

    # Show network animation frames
    for i, (frame, message) in enumerate(zip(POWERUP_FRAMES, CONNECT_MESSAGES)):
        console.clear()
        console.print(f"[bold cyan]{HOMIE_LOGO}[/]")

        # Color the frame based on progress
        if i < 2:
            frame_style = "dim"
        elif i < 4:
            frame_style = "yellow"
        else:
            frame_style = "green bold"

        console.print(f"[{frame_style}]{frame}[/]")

        # Progress bar
        progress = "█" * (i + 1) * 4 + "░" * (20 - (i + 1) * 4)
        console.print(f"\n    [{frame_style}][{progress}][/]")

        # Message
        if i == len(CONNECT_MESSAGES) - 1:
            console.print(f"\n    [bold green]◉ {message}[/] as [bold]{name}[/]")
        else:
            console.print(f"\n    [dim]◌ {message}[/]")

        time.sleep(0.4)

    time.sleep(0.5)
    console.clear()


def create_peers_table(peers: list[Peer]) -> Table:
    """Create a table showing all peers."""
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("NAME", style="green", no_wrap=True)
    table.add_column("IP", style="dim")
    table.add_column("CPU", justify="right")
    table.add_column("RAM", justify="right")
    table.add_column("GPU", style="yellow")
    table.add_column("STATUS", justify="center")

    for peer in sorted(peers, key=lambda p: p.name):
        # CPU bar visualization
        cpu_blocks = int(peer.cpu_percent_used / 25)
        cpu_bar = "▓" * cpu_blocks + "░" * (4 - cpu_blocks)

        # Status indicator
        if peer.status == "idle":
            status = Text("● idle", style="green")
        else:
            status = Text("● busy", style="yellow")

        # GPU display
        gpu = peer.gpu_name if peer.gpu_name else "-"
        if peer.gpu_memory_free_gb:
            gpu = f"{peer.gpu_name} ({peer.gpu_memory_free_gb:.1f}G free)"

        table.add_row(
            peer.name,
            peer.ip,
            f"{peer.cpu_percent_used:3.0f}% {cpu_bar}",
            f"{peer.ram_free_gb:.1f} GB",
            gpu,
            status,
        )

    return table


def create_header(name: str, ip: str) -> Panel:
    """Create the header panel."""
    return Panel(
        Text(f"🏠 HOMIE COMPUTE\n{name}@{ip}", justify="center", style="bold blue"),
        style="blue",
        padding=(0, 2),
    )


def create_stats_panel(stats: dict) -> Panel:
    """Create local machine stats panel."""
    content = Text()
    content.append(f"CPU: {stats['cpu_count']} cores\n", style="dim")
    content.append(f"RAM: {stats['ram_total']:.1f} GB\n", style="dim")
    if stats.get("gpu"):
        content.append(f"GPU: {stats['gpu']}\n", style="yellow")
    return Panel(content, title="Your Machine", border_style="dim")


def create_cluster_summary(peers: list[Peer]) -> str:
    """Create cluster summary text."""
    if not peers:
        return "[dim]No homies online[/]"

    total_ram = sum(p.ram_free_gb for p in peers)
    gpus = [p for p in peers if p.gpu_name]
    busy = sum(1 for p in peers if p.status == "busy")

    parts = [
        f"[green]{len(peers)}[/] peers",
        f"[cyan]{total_ram:.1f} GB[/] RAM",
        f"[yellow]{len(gpus)}[/] GPUs",
    ]
    if busy:
        parts.append(f"[yellow]{busy}[/] busy")

    return " │ ".join(parts)


def create_dashboard_layout(
    name: str,
    ip: str,
    peers: list[Peer],
    running_jobs: list = None,
) -> Layout:
    """Create the full dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )

    # Header
    layout["header"].update(create_header(name, ip))

    # Main content
    main_layout = Layout()
    if peers:
        peers_panel = Panel(
            create_peers_table(peers),
            title="[bold]HOMIES ONLINE[/]",
            subtitle=create_cluster_summary(peers),
            border_style="green",
        )
    else:
        peers_panel = Panel(
            Text("Waiting for homies to join...\n\n[dim]Make sure they're running 'homie up' with the same group secret[/]", justify="center"),
            title="[bold]HOMIES ONLINE[/]",
            border_style="dim",
        )
    main_layout.update(peers_panel)
    layout["main"].update(main_layout)

    # Footer
    footer_text = Text("Press Ctrl+C to stop", justify="center", style="dim")
    layout["footer"].update(Panel(footer_text, border_style="dim"))

    return layout


class LiveDashboard:
    """Live-updating dashboard for homie up."""

    def __init__(
        self,
        name: str,
        discovery: Discovery,
        worker: Optional[Worker] = None,
    ):
        self.name = name
        self.discovery = discovery
        self.worker = worker
        self.ip = get_local_ip()
        self._events: list[str] = []

    def add_event(self, message: str) -> None:
        """Add an event to the log."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._events.append(f"[dim]{timestamp}[/] {message}")
        # Keep only last 5 events
        self._events = self._events[-5:]

    def run(self) -> None:
        """Run the live dashboard."""
        with Live(
            self._render(),
            console=console,
            refresh_per_second=1,
            screen=False,
        ) as live:
            try:
                while True:
                    live.update(self._render())
                    # Write peer cache for other commands to use
                    self.discovery.write_peer_cache()
                    import time
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

    def _render(self) -> Layout:
        """Render the dashboard."""
        peers = self.discovery.get_peers()
        running_jobs = self.worker.get_running_jobs() if self.worker else []

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="peers"),
            Layout(name="events", size=8),
        )

        # Header
        layout["header"].update(create_header(self.name, self.ip))

        # Peers
        if peers:
            peers_panel = Panel(
                create_peers_table(peers),
                title="[bold]HOMIES ONLINE[/]",
                subtitle=create_cluster_summary(peers),
                border_style="green",
            )
        else:
            peers_panel = Panel(
                Text("Searching for homies...", justify="center", style="dim"),
                title="[bold]HOMIES ONLINE[/]",
                border_style="dim",
            )
        layout["peers"].update(peers_panel)

        # Events
        if self._events:
            events_text = Text("\n".join(self._events))
        else:
            events_text = Text("Waiting for activity...", style="dim")
        layout["events"].update(
            Panel(events_text, title="[bold]ACTIVITY[/]", border_style="dim")
        )

        return layout


def print_startup_banner(
    name: str,
    ip: str,
    port: int,
    discovery_port: int,
    docker_ok: bool,
    gpu_ok: bool,
) -> None:
    """Print the startup banner."""
    stats = get_system_stats()

    content = Text()
    content.append("🏠 HOMIE COMPUTE\n", style="bold blue")
    content.append("─" * 35 + "\n", style="dim")
    content.append(f"Name: ", style="dim")
    content.append(f"{name}\n", style="green bold")
    content.append(f"IP: ", style="dim")
    content.append(f"{ip}\n")
    content.append(f"Port: ", style="dim")
    content.append(f"{port}\n")
    content.append("─" * 35 + "\n", style="dim")
    content.append(f"CPU: ", style="dim")
    content.append(f"{stats.cpu_count} cores\n")
    content.append(f"RAM: ", style="dim")
    content.append(f"{stats.ram_total_gb:.1f} GB\n")
    if stats.gpu_name:
        content.append(f"GPU: ", style="dim")
        content.append(f"{stats.gpu_name}\n", style="yellow")

    console.print(Panel(content, border_style="blue"))
    console.print()

    # Status indicators
    if docker_ok:
        console.print("  [green]✓[/] Docker sandbox ready")
    else:
        console.print("  [red]✗[/] Docker not available - jobs will fail")

    console.print(f"  [green]✓[/] Discovery broadcasting on :{discovery_port}")
    console.print(f"  [green]✓[/] Worker listening on :{port}")

    if gpu_ok:
        console.print("  [green]✓[/] GPU passthrough available")

    console.print()


def print_peers_table(peers: list[Peer]) -> None:
    """Print peers table (for homie peers command)."""
    if not peers:
        console.print("[yellow]No homies found on the network[/]")
        console.print("[dim]Make sure they're running 'homie up' with the same group secret[/]")
        return

    console.print(
        Panel(
            create_peers_table(peers),
            title="[bold]🏠 HOMIES ON NETWORK[/]",
            border_style="green",
        )
    )
    console.print()
    console.print(f"[dim]{create_cluster_summary(peers)}[/]")


def print_job_start(peer_name: str, job_id: str, script: str, args: list[str]) -> None:
    """Print job start message."""
    content = Text()
    content.append(f"Job ID: ", style="dim")
    content.append(f"{job_id}\n")
    content.append(f"Script: ", style="dim")
    content.append(f"{script}\n")
    if args:
        content.append(f"Args: ", style="dim")
        content.append(f"{' '.join(args)}\n")

    console.print(Panel(content, title=f"[bold]Sending to {peer_name}[/]", border_style="cyan"))
    console.print()


def print_job_output(peer_name: str, line: str) -> None:
    """Print a line of job output."""
    console.print(f"[dim][{peer_name}][/] {line}")


def print_job_complete(runtime: float, output_files: list[str]) -> None:
    """Print job completion message."""
    content = Text()
    content.append(f"Runtime: ", style="dim")
    content.append(f"{runtime:.1f}s\n")
    if output_files:
        content.append(f"Downloaded: ", style="dim")
        content.append(", ".join(output_files))

    console.print()
    console.print(Panel(content, title="[bold green]✓ Job Complete[/]", border_style="green"))


def print_job_error(error: str) -> None:
    """Print job error message."""
    console.print()
    console.print(Panel(Text(error, style="red"), title="[bold red]✗ Job Failed[/]", border_style="red"))
