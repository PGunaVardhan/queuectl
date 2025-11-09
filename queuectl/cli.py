"""
CLI interface for queuectl - because terminals are still cool in 2025.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from queuectl.storage import JobStore
from queuectl.worker import WorkerManager
from queuectl.models import JobState

app = typer.Typer(help="A job queue that actually works")
worker_app = typer.Typer(help="Manage worker processes")
dlq_app = typer.Typer(help="Dead Letter Queue operations")
config_app = typer.Typer(help="Configuration management")

app.add_typer(worker_app, name="worker")
app.add_typer(dlq_app, name="dlq")
app.add_typer(config_app, name="config")

console = Console()
store = JobStore()


@app.command()
def enqueue(job_json: str):
    """
    Enqueue a new job. Pass JSON with id, command, and optional max_retries.
    
    Example: queuectl enqueue '{"id":"job1","command":"sleep 2"}'
    """
    try:
        job_data = json.loads(job_json)
        job_id = store.add_job(
            job_id=job_data.get("id"),
            command=job_data["command"],
            max_retries=job_data.get("max_retries", store.get_config("max_retries")),
        )
        console.print(f"[green]✓[/green] Job {job_id} enqueued")
    except json.JSONDecodeError:
        console.print("[red]✗[/red] Invalid JSON", err=True)
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", err=True)
        sys.exit(1)


@worker_app.command("start")
def worker_start(count: int = typer.Option(1, help="Number of workers to start")):
    """Start worker processes to consume the queue."""
    console.print(f"[blue]→[/blue] Starting {count} worker(s)...")
    manager = WorkerManager(store)
    
    try:
        manager.start_workers(count)
        console.print(f"[green]✓[/green] Workers started. Press Ctrl+C to stop gracefully.")
        manager.wait()
    except KeyboardInterrupt:
        console.print("\n[yellow]![/yellow] Shutting down gracefully...")
        manager.stop_workers()
        console.print("[green]✓[/green] All workers stopped")


@worker_app.command("stop")
def worker_stop():
    """Stop all running workers gracefully."""
    manager = WorkerManager(store)
    manager.stop_workers()
    console.print("[green]✓[/green] Stop signal sent to workers")


@app.command()
def status():
    """Show queue status and worker information."""
    stats = store.get_stats()
    
    table = Table(title="Queue Status")
    table.add_column("State", style="cyan")
    table.add_column("Count", justify="right", style="magenta")
    
    for state in JobState:
        count = stats.get(state.value, 0)
        table.add_row(state.value, str(count))
    
    console.print(table)
    
    # Worker info
    manager = WorkerManager(store)
    active = manager.count_active_workers()
    console.print(f"\n[blue]Active workers:[/blue] {active}")


@app.command()
def list(
    state: Optional[str] = typer.Option(None, help="Filter by state"),
    limit: int = typer.Option(50, help="Max jobs to show"),
):
    """List jobs, optionally filtered by state."""
    jobs = store.list_jobs(state=state, limit=limit)
    
    if not jobs:
        console.print("[yellow]No jobs found[/yellow]")
        return
    
    table = Table(title=f"Jobs ({len(jobs)})")
    table.add_column("ID", style="cyan")
    table.add_column("Command", style="white")
    table.add_column("State", style="magenta")
    table.add_column("Attempts", justify="right")
    table.add_column("Created", style="dim")
    
    for job in jobs:
        # Truncate long commands
        cmd = job["command"][:50] + "..." if len(job["command"]) > 50 else job["command"]
        table.add_row(
            job["id"],
            cmd,
            job["state"],
            f"{job['attempts']}/{job['max_retries']}",
            job["created_at"][:19],  # trim microseconds
        )
    
    console.print(table)


@dlq_app.command("list")
def dlq_list(limit: int = typer.Option(50, help="Max jobs to show")):
    """List jobs in the Dead Letter Queue."""
    jobs = store.list_jobs(state="dead", limit=limit)
    
    if not jobs:
        console.print("[green]DLQ is empty - nice![/green]")
        return
    
    table = Table(title=f"Dead Letter Queue ({len(jobs)} failed jobs)")
    table.add_column("ID", style="cyan")
    table.add_column("Command", style="white")
    table.add_column("Attempts", justify="right")
    table.add_column("Last Error", style="red")
    
    for job in jobs:
        cmd = job["command"][:40] + "..." if len(job["command"]) > 40 else job["command"]
        error = job.get("error", "Unknown")[:60]
        table.add_row(job["id"], cmd, str(job["attempts"]), error)
    
    console.print(table)


@dlq_app.command("retry")
def dlq_retry(job_id: str):
    """Retry a failed job from the DLQ."""
    try:
        store.retry_job(job_id)
        console.print(f"[green]✓[/green] Job {job_id} moved back to pending")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}", err=True)
        sys.exit(1)


@config_app.command("set")
def config_set(key: str, value: str):
    """
    Set a configuration value.
    
    Available keys: max-retries, backoff-base
    """
    key_map = {
        "max-retries": "max_retries",
        "backoff-base": "backoff_base",
    }
    
    if key not in key_map:
        console.print(f"[red]✗[/red] Unknown config key: {key}", err=True)
        console.print(f"Available keys: {', '.join(key_map.keys())}")
        sys.exit(1)
    
    try:
        store.set_config(key_map[key], int(value))
        console.print(f"[green]✓[/green] {key} = {value}")
    except ValueError:
        console.print(f"[red]✗[/red] Value must be an integer", err=True)
        sys.exit(1)


@config_app.command("get")
def config_get(key: Optional[str] = None):
    """Show configuration values."""
    key_map = {
        "max-retries": "max_retries",
        "backoff-base": "backoff_base",
    }
    
    if key:
        if key not in key_map:
            console.print(f"[red]✗[/red] Unknown config key: {key}", err=True)
            sys.exit(1)
        value = store.get_config(key_map[key])
        console.print(f"{key}: {value}")
    else:
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="magenta")
        
        for display_key, internal_key in key_map.items():
            value = store.get_config(internal_key)
            table.add_row(display_key, str(value))
        
        console.print(table)


@app.command()
def cleanup(days: int = typer.Option(7, help="Delete completed jobs older than N days")):
    """Clean up old completed jobs."""
    deleted = store.cleanup_old_jobs(days)
    console.print(f"[green]✓[/green] Deleted {deleted} old job(s)")


def main():
    app()


if __name__ == "__main__":
    main()