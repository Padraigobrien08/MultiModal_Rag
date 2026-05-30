import uuid
import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

app = typer.Typer(help="Stepwise — turn tutorial videos into queryable steps")
console = Console()


@app.command()
def ingest(url: str, title: str = typer.Option(None, help="Optional title override")):
    """Ingest a YouTube tutorial URL and index its steps."""
    from stepwise.ingestion import ingest_youtube
    from stepwise.alignment import align_segments
    from stepwise.structuring import structure_steps
    from stepwise.indexing import index_tutorial
    from stepwise.models import Tutorial

    with console.status(f"[bold green]Ingesting {url}..."):
        artifacts = ingest_youtube(url)

    console.print(f"[green]✓[/green] Extracted {len(artifacts['transcript'])} transcript entries, {len(artifacts['frames'])} frames")

    with console.status("[bold green]Aligning segments..."):
        segments = align_segments(artifacts["transcript"], artifacts["frames"])

    console.print(f"[green]✓[/green] Built {len(segments)} segments")

    tutorial_id = str(uuid.uuid4())
    with console.status("[bold green]Structuring steps with Claude..."):
        steps = structure_steps(tutorial_id, segments)

    console.print(f"[green]✓[/green] Extracted {len(steps)} steps")

    with console.status("[bold green]Indexing..."):
        tutorial = Tutorial(
            id=tutorial_id,
            source_url=url,
            title=title or artifacts["video_id"],
            source_type="youtube",
            steps=steps,
            meta={"video_id": artifacts["video_id"]},
        )
        index_tutorial(tutorial)

    console.print(f"\n[bold]Done.[/bold] Tutorial ID: [cyan]{tutorial_id}[/cyan]")
    console.print(f"Indexed [bold]{len(steps)}[/bold] steps.")


@app.command()
def query(
    question: str,
    tutorial_id: str = typer.Option(None, "--tutorial", "-t", help="Limit to a specific tutorial"),
    top_k: int = typer.Option(5, "--top-k", "-k"),
):
    """Ask a question about ingested tutorials."""
    from stepwise.retrieval import query_steps

    with console.status("[bold green]Searching..."):
        result = query_steps(question, tutorial_id=tutorial_id, top_k=top_k)

    console.print(f"\n[bold cyan]Answer:[/bold cyan] {result['answer']}\n")

    table = Table(title="Retrieved Steps", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Step", style="bold")
    table.add_column("Time", width=8)
    table.add_column("Visual", width=6)

    for s in result["steps"]:
        ts = f"{s['timestamp_start']:.0f}s" if s.get("timestamp_start") is not None else "—"
        has_visual = "yes" if s.get("visual_reference") else "—"
        table.add_row(str(s["step_number"]), s["text"][:80], ts, has_visual)

    console.print(table)


if __name__ == "__main__":
    app()
