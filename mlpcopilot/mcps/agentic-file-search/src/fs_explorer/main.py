"""
CLI entry point for the FsExplorer agent.

Provides a command-line interface for running filesystem exploration tasks
with rich, detailed output showing each step of the workflow.
"""

import json
import asyncio
import os
from datetime import datetime
from pathlib import Path

from typer import Typer, Option, Argument, Context, BadParameter, Exit
from typing import Annotated, Any
from rich.markdown import Markdown
from rich.panel import Panel
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .embeddings import EmbeddingProvider
from .index_config import resolve_db_path
from .indexing import IndexingPipeline, SchemaDiscovery
from .storage import DuckDBStorage
from .agent import set_index_context, clear_index_context
from .workflow import (
    workflow,
    InputEvent,
    ToolCallEvent,
    GoDeeperEvent,
    AskHumanEvent,
    HumanAnswerEvent,
    get_agent,
    reset_agent,
)
from .exploration_trace import ExplorationTrace, extract_cited_sources

app = Typer()
schema_app = Typer(help="Manage metadata schemas for indexed corpora.")
app.add_typer(schema_app, name="schema")


# Tool icons for visual distinction
TOOL_ICONS = {
    "scan_folder": "📂",
    "preview_file": "👁️",
    "parse_file": "📖",
    "read": "📄",
    "grep": "🔍",
    "glob": "🔎",
    "semantic_search": "🧠",
    "get_document": "📚",
    "list_indexed_documents": "🗂️",
}

# Phase detection based on tool usage
PHASE_DESCRIPTIONS = {
    "scan_folder": ("Phase 1", "Parallel Document Scan", "cyan"),
    "preview_file": ("Phase 1/2", "Quick Preview", "cyan"),
    "parse_file": ("Phase 2", "Deep Dive", "green"),
    "read": ("Reading", "Text File", "blue"),
    "grep": ("Searching", "Pattern Match", "yellow"),
    "glob": ("Finding", "File Search", "yellow"),
    "semantic_search": ("Indexed", "Semantic Retrieval", "magenta"),
    "get_document": ("Indexed", "Document Fetch", "green"),
    "list_indexed_documents": ("Indexed", "Corpus Listing", "blue"),
}


def _load_metadata_profile(path_value: str | None) -> dict[str, Any] | None:
    if path_value is None:
        return None
    resolved = Path(path_value).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise BadParameter(f"Metadata profile file not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text())
    except json.JSONDecodeError as exc:
        raise BadParameter(
            f"Metadata profile file is not valid JSON: {resolved}"
        ) from exc
    if not isinstance(payload, dict):
        raise BadParameter("Metadata profile JSON must be an object.")
    return payload


def format_tool_panel(event: ToolCallEvent, step_number: int) -> Panel:
    """Create a richly formatted panel for a tool call event."""
    tool_name = event.tool_name
    icon = TOOL_ICONS.get(tool_name, "🔧")
    phase_info = PHASE_DESCRIPTIONS.get(tool_name, ("Action", "Tool Call", "yellow"))
    phase_label, phase_desc, color = phase_info

    # Build the content
    lines = []

    # Tool and target info
    if "directory" in event.tool_input:
        target = event.tool_input["directory"]
        lines.append(f"**Target Directory:** `{target}`")
    elif "file_path" in event.tool_input:
        target = event.tool_input["file_path"]
        lines.append(f"**Target File:** `{target}`")

    # Additional parameters
    other_params = {
        k: v for k, v in event.tool_input.items() if k not in ("directory", "file_path")
    }
    if other_params:
        lines.append(f"**Parameters:** `{json.dumps(other_params)}`")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Reasoning (this is the key part for visibility)
    lines.append("**Agent's Reasoning:**")
    lines.append("")
    lines.append(event.reason)

    content = "\n".join(lines)

    # Create title with step number and phase
    title = f"{icon} Step {step_number}: {tool_name} [{phase_label}: {phase_desc}]"

    return Panel(
        Markdown(content),
        title=title,
        title_align="left",
        border_style=f"bold {color}",
        padding=(1, 2),
    )


def format_navigation_panel(event: GoDeeperEvent, step_number: int) -> Panel:
    """Create a panel for directory navigation events."""
    content = f"""**Navigating to:** `{event.directory}`

---

**Agent's Reasoning:**

{event.reason}
"""
    return Panel(
        Markdown(content),
        title=f"📁 Step {step_number}: Navigate to Directory",
        title_align="left",
        border_style="bold magenta",
        padding=(1, 2),
    )


def print_workflow_header(console: Console, task: str, folder: str) -> None:
    """Print a header showing the task being executed."""
    console.print()
    header = Table.grid(padding=(0, 2))
    header.add_column(style="bold cyan", justify="right")
    header.add_column()

    header.add_row("🤖 FsExplorer Agent", "")
    header.add_row("📋 Task:", task)
    header.add_row("📁 Folder:", folder)
    header.add_row("🕐 Started:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    console.print(
        Panel(
            header,
            border_style="bold blue",
            title="Starting Exploration",
            title_align="left",
        )
    )
    console.print()


def print_workflow_summary(
    console: Console,
    agent,
    step_count: int,
    trace: ExplorationTrace,
    cited_sources: list[str],
) -> None:
    """Print a summary of the workflow execution."""
    usage = agent.token_usage

    # Create summary table
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold", justify="right")
    summary.add_column()

    summary.add_row("Total Steps:", str(step_count))
    summary.add_row("API Calls:", str(usage.api_calls))
    summary.add_row("Documents Scanned:", str(usage.documents_scanned))
    summary.add_row("Documents Parsed:", str(usage.documents_parsed))
    summary.add_row("", "")
    summary.add_row("Prompt Tokens:", f"{usage.prompt_tokens:,}")
    summary.add_row("Completion Tokens:", f"{usage.completion_tokens:,}")
    summary.add_row("Total Tokens:", f"{usage.total_tokens:,}")
    summary.add_row("", "")

    # Cost calculation
    input_cost, output_cost, total_cost = usage._calculate_cost()
    summary.add_row("Est. Input Cost:", f"${input_cost:.4f}")
    summary.add_row("Est. Output Cost:", f"${output_cost:.4f}")
    summary.add_row("Est. Total Cost:", f"${total_cost:.4f}")

    console.print()
    console.print(
        Panel(
            summary,
            title="📊 Workflow Summary",
            title_align="left",
            border_style="bold blue",
        )
    )

    if trace.step_path:
        path_markdown = "\n".join(f"- `{entry}`" for entry in trace.step_path)
        console.print()
        console.print(
            Panel(
                Markdown(path_markdown),
                title="🧭 Exploration Path",
                title_align="left",
                border_style="bold cyan",
            )
        )

    referenced_documents = trace.sorted_documents()
    if referenced_documents:
        docs_markdown = "\n".join(f"- `{doc}`" for doc in referenced_documents)
        console.print()
        console.print(
            Panel(
                Markdown(docs_markdown),
                title="📚 Referenced Documents (Tool Calls)",
                title_align="left",
                border_style="bold green",
            )
        )

    if cited_sources:
        sources_markdown = "\n".join(f"- `{source}`" for source in cited_sources)
        console.print()
        console.print(
            Panel(
                Markdown(sources_markdown),
                title="🔖 Cited Sources (Final Answer)",
                title_align="left",
                border_style="bold yellow",
            )
        )


async def run_workflow(
    task: str,
    folder: str = ".",
    *,
    use_index: bool = False,
    db_path: str | None = None,
) -> None:
    """
    Execute the exploration workflow with detailed step-by-step output.

    Args:
        task: The user's task/question to answer.
    """
    console = Console()
    resolved_folder = os.path.abspath(folder)
    if not os.path.exists(resolved_folder) or not os.path.isdir(resolved_folder):
        console.print(
            Panel(
                Text(f"No such directory: {resolved_folder}", style="bold red"),
                title="❌ Error",
                title_align="left",
                border_style="bold red",
            )
        )
        return

    resolved_db_path: str | None = None
    index_storage: DuckDBStorage | None = None
    if use_index:
        resolved_db_path = resolve_db_path(db_path)
        storage = DuckDBStorage(resolved_db_path)
        corpus_id = storage.get_corpus_id(resolved_folder)
        if corpus_id is None:
            console.print(
                Panel(
                    Text(
                        "No index found for this folder. "
                        "Run `explore index <folder>` first.",
                        style="bold red",
                    ),
                    title="❌ Missing Index",
                    title_align="left",
                    border_style="bold red",
                )
            )
            return
        index_storage = storage
        set_index_context(resolved_folder, resolved_db_path)
    else:
        clear_index_context()

    try:
        # Reset agent for fresh state
        reset_agent()

        # Print header
        print_workflow_header(console, task, resolved_folder)
        trace = ExplorationTrace(root_directory=resolved_folder)

        step_number = 0
        handler = workflow.run(
            start_event=InputEvent(
                task=task,
                folder=resolved_folder,
                use_index=use_index,
            )
        )

        with console.status(status="[bold cyan]🔄 Analyzing task...") as status:
            async for event in handler.stream_events():
                if isinstance(event, ToolCallEvent):
                    step_number += 1
                    resolved_document_path: str | None = None
                    if event.tool_name == "get_document":
                        doc_id = event.tool_input.get("doc_id")
                        if (
                            index_storage is not None
                            and isinstance(doc_id, str)
                            and doc_id
                        ):
                            document = index_storage.get_document(doc_id=doc_id)
                            if document and not document["is_deleted"]:
                                resolved_document_path = str(document["absolute_path"])

                    trace.record_tool_call(
                        step_number=step_number,
                        tool_name=event.tool_name,
                        tool_input=event.tool_input,
                        resolved_document_path=resolved_document_path,
                    )

                    # Update status based on tool
                    icon = TOOL_ICONS.get(event.tool_name, "🔧")
                    if event.tool_name == "scan_folder":
                        status.update(
                            f"[bold cyan]{icon} Scanning documents in parallel..."
                        )
                    elif event.tool_name == "parse_file":
                        status.update(
                            f"[bold green]{icon} Reading document in detail..."
                        )
                    elif event.tool_name == "preview_file":
                        status.update(f"[bold cyan]{icon} Quick preview of document...")
                    elif event.tool_name == "semantic_search":
                        status.update(f"[bold magenta]{icon} Searching index...")
                    elif event.tool_name == "get_document":
                        status.update(f"[bold green]{icon} Reading indexed document...")
                    elif event.tool_name == "list_indexed_documents":
                        status.update(f"[bold blue]{icon} Listing indexed documents...")
                    else:
                        status.update(
                            f"[bold yellow]{icon} Executing {event.tool_name}..."
                        )

                    # Print the detailed panel
                    panel = format_tool_panel(event, step_number)
                    console.print(panel)
                    console.print()

                    status.update("[bold cyan]🔄 Processing results...")
                elif isinstance(event, GoDeeperEvent):
                    step_number += 1
                    trace.record_go_deeper(
                        step_number=step_number, directory=event.directory
                    )
                    panel = format_navigation_panel(event, step_number)
                    console.print(panel)
                    console.print()
                    status.update("[bold cyan]🔄 Exploring directory...")

                elif isinstance(event, AskHumanEvent):
                    status.stop()
                    console.print()

                    # Create a nice prompt panel
                    question_panel = Panel(
                        Markdown(
                            f"**Question:** {event.question}\n\n**Why I'm asking:** {event.reason}"
                        ),
                        title="❓ Human Input Required",
                        title_align="left",
                        border_style="bold red",
                    )
                    console.print(question_panel)

                    answer = console.input("[bold cyan]Your answer:[/] ")
                    while answer.strip() == "":
                        console.print("[bold red]Please provide an answer.[/]")
                        answer = console.input("[bold cyan]Your answer:[/] ")

                    handler.ctx.send_event(HumanAnswerEvent(response=answer.strip()))
                    console.print()
                    status.start()
                    status.update("[bold cyan]🔄 Processing your response...")

            # Get final result
            result = await handler
            status.update("[bold green]✨ Preparing final answer...")
            await asyncio.sleep(0.1)
            status.stop()

        # Print final result with prominent styling
        console.print()
        if result.final_result:
            final_panel = Panel(
                Markdown(result.final_result),
                title="✅ Final Answer",
                title_align="left",
                border_style="bold green",
                padding=(1, 2),
            )
            console.print(final_panel)
        elif result.error:
            error_panel = Panel(
                Text(result.error, style="bold red"),
                title="❌ Error",
                title_align="left",
                border_style="bold red",
            )
            console.print(error_panel)

        # Print workflow summary
        agent = get_agent()
        cited_sources = extract_cited_sources(result.final_result)
        print_workflow_summary(console, agent, step_number, trace, cited_sources)
    finally:
        clear_index_context()


@app.callback(invoke_without_command=True)
def main(
    ctx: Context,
    task: Annotated[
        str | None,
        Option(
            "--task",
            "-t",
            help="Task that the FsExplorer Agent has to perform while exploring the current directory.",
        ),
    ] = None,
    folder: Annotated[
        str,
        Option(
            "--folder",
            "-f",
            help="Folder to explore. Defaults to the current directory.",
        ),
    ] = ".",
    use_index: Annotated[
        bool,
        Option(
            "--use-index",
            help="Use indexed retrieval tools for this run (requires prior indexing).",
        ),
    ] = False,
    db_path: Annotated[
        str | None,
        Option("--db-path", help="Path to DuckDB index file."),
    ] = None,
) -> None:
    """
    Explore documents with an agent, build indexes, and manage schema metadata.

    Backward-compatible mode:
    - `explore --task "..." [--folder ...]`
    """
    if ctx.invoked_subcommand is not None:
        return

    if task is None or not task.strip():
        raise BadParameter("`--task` is required unless you run a subcommand.")

    effective_use_index = use_index
    if (
        not effective_use_index
        and os.getenv("FS_EXPLORER_AUTO_INDEX", "").strip() == "1"
    ):
        try:
            resolved_folder = os.path.abspath(folder)
            resolved_db = resolve_db_path(db_path)
            storage = DuckDBStorage(resolved_db, read_only=True, initialize=False)
            if storage.get_corpus_id(resolved_folder) is not None:
                effective_use_index = True
            storage.close()
        except Exception:
            pass

    asyncio.run(
        run_workflow(task, folder, use_index=effective_use_index, db_path=db_path)
    )


@app.command("index")
def index_command(
    folder: Annotated[
        str,
        Argument(help="Folder to index recursively."),
    ] = ".",
    db_path: Annotated[
        str | None,
        Option("--db-path", help="Path to DuckDB index file."),
    ] = None,
    discover_schema: Annotated[
        bool,
        Option(
            "--discover-schema",
            help="Auto-discover metadata schema and set it active for this corpus.",
        ),
    ] = False,
    schema_name: Annotated[
        str | None,
        Option("--schema-name", help="Use an existing stored schema by name."),
    ] = None,
    with_metadata: Annotated[
        bool,
        Option(
            "--with-metadata",
            help=(
                "Enable langextract metadata extraction (requires API key). "
                "Also enables schema discovery if not explicitly requested."
            ),
        ),
    ] = False,
    metadata_profile_path: Annotated[
        str | None,
        Option(
            "--metadata-profile",
            help=(
                "Path to JSON profile defining dynamic langextract metadata fields "
                "and prompt. Implies --with-metadata."
            ),
        ),
    ] = None,
    with_embeddings: Annotated[
        bool,
        Option(
            "--with-embeddings",
            help="Generate vector embeddings for indexed chunks (requires GOOGLE_API_KEY).",
        ),
    ] = False,
) -> None:
    """Build or refresh an index for a folder."""
    console = Console()
    resolved_db_path = resolve_db_path(db_path)
    storage = DuckDBStorage(resolved_db_path)

    embedding_provider: EmbeddingProvider | None = None
    if with_embeddings:
        try:
            embedding_provider = EmbeddingProvider()
        except ValueError as exc:
            raise BadParameter(str(exc)) from exc

    pipeline = IndexingPipeline(
        storage=storage,
        embedding_provider=embedding_provider,
    )
    metadata_profile = _load_metadata_profile(metadata_profile_path)
    effective_with_metadata = with_metadata or metadata_profile is not None

    if effective_with_metadata and metadata_profile is None:
        console.print(
            "[bold cyan]🔍 Analyzing corpus to generate metadata profile...[/]"
        )

    try:
        effective_discover_schema = discover_schema or effective_with_metadata
        result = pipeline.index_folder(
            folder,
            discover_schema=effective_discover_schema,
            schema_name=schema_name,
            with_metadata=effective_with_metadata,
            metadata_profile=metadata_profile,
        )
    except ValueError as exc:
        raise BadParameter(str(exc)) from exc

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold", justify="right")
    summary.add_column()
    summary.add_row("DB Path:", resolved_db_path)
    summary.add_row("Corpus ID:", result.corpus_id)
    summary.add_row("Indexed Files:", str(result.indexed_files))
    summary.add_row("Skipped Files:", str(result.skipped_files))
    summary.add_row("Deleted Files:", str(result.deleted_files))
    summary.add_row("Chunks Written:", str(result.chunks_written))
    summary.add_row("Active Documents:", str(result.active_documents))
    summary.add_row("Embeddings Written:", str(result.embeddings_written))
    summary.add_row("Schema Used:", result.schema_used or "<none>")
    summary.add_row(
        "Metadata Mode:",
        "langextract" if effective_with_metadata else "heuristic",
    )
    if metadata_profile_path:
        profile_label = str(Path(metadata_profile_path).expanduser().resolve())
    elif effective_with_metadata:
        profile_label = "<auto-discovered>"
    else:
        profile_label = "<none>"
    summary.add_row("Metadata Profile:", profile_label)

    console.print(Panel(summary, title="📦 Index Complete", border_style="bold green"))


@app.command("query")
def query_command(
    task: Annotated[
        str,
        Option(
            "--task",
            "-t",
            help="Question to answer using indexed retrieval tools.",
        ),
    ],
    folder: Annotated[
        str,
        Option(
            "--folder",
            "-f",
            help="Folder whose index should be queried.",
        ),
    ] = ".",
    db_path: Annotated[
        str | None,
        Option("--db-path", help="Path to DuckDB index file."),
    ] = None,
) -> None:
    """Run the agent with indexed retrieval enabled."""
    asyncio.run(run_workflow(task, folder, use_index=True, db_path=db_path))


@schema_app.command("discover")
def schema_discover_command(
    folder: Annotated[
        str,
        Argument(help="Folder to inspect for schema discovery."),
    ] = ".",
    db_path: Annotated[
        str | None,
        Option("--db-path", help="Path to DuckDB index file."),
    ] = None,
    name: Annotated[
        str | None,
        Option("--name", help="Override discovered schema name."),
    ] = None,
    activate: Annotated[
        bool,
        Option(
            "--activate/--no-activate",
            help="Set schema as active for the corpus.",
        ),
    ] = True,
    with_metadata: Annotated[
        bool,
        Option(
            "--with-metadata",
            help="Include langextract metadata fields in discovered schema.",
        ),
    ] = False,
    metadata_profile_path: Annotated[
        str | None,
        Option(
            "--metadata-profile",
            help=(
                "Path to JSON profile defining dynamic langextract metadata fields "
                "and prompt. Implies --with-metadata."
            ),
        ),
    ] = None,
) -> None:
    """Auto-discover and store a metadata schema for a folder."""
    console = Console()
    resolved_folder = str(os.path.abspath(folder))
    if not os.path.isdir(resolved_folder):
        raise BadParameter(f"No such directory: {resolved_folder}")

    resolved_db_path = resolve_db_path(db_path)
    storage = DuckDBStorage(resolved_db_path)
    corpus_id = storage.get_or_create_corpus(resolved_folder)
    metadata_profile = _load_metadata_profile(metadata_profile_path)
    effective_with_metadata = with_metadata or metadata_profile is not None

    if effective_with_metadata and metadata_profile is None:
        console.print(
            "[bold cyan]🔍 Analyzing corpus to generate metadata profile...[/]"
        )

    discovery = SchemaDiscovery()
    discovered = discovery.discover_from_folder(
        resolved_folder,
        with_langextract=effective_with_metadata,
        metadata_profile=metadata_profile,
    )
    schema_name = name or str(
        discovered.get("name", f"auto_{os.path.basename(resolved_folder)}")
    )
    discovered["name"] = schema_name
    schema_id = storage.save_schema(
        corpus_id=corpus_id,
        name=schema_name,
        schema_def=discovered,
        is_active=activate,
    )

    output = Table.grid(padding=(0, 2))
    output.add_column(style="bold", justify="right")
    output.add_column()
    output.add_row("DB Path:", resolved_db_path)
    output.add_row("Corpus ID:", corpus_id)
    output.add_row("Schema ID:", schema_id)
    output.add_row("Schema Name:", schema_name)
    output.add_row("Active:", str(activate))
    output.add_row("Field Count:", str(len(discovered.get("fields", []))))
    output.add_row(
        "Metadata Mode:", "langextract" if effective_with_metadata else "heuristic"
    )
    if metadata_profile_path:
        profile_label = str(Path(metadata_profile_path).expanduser().resolve())
    elif effective_with_metadata:
        profile_label = "<auto-discovered>"
    else:
        profile_label = "<none>"
    output.add_row("Metadata Profile:", profile_label)

    console.print(Panel(output, title="🧩 Schema Saved", border_style="bold cyan"))
    console.print_json(json.dumps(discovered, indent=2))


@schema_app.command("show")
def schema_show_command(
    folder: Annotated[
        str,
        Argument(help="Folder whose schemas should be listed."),
    ] = ".",
    db_path: Annotated[
        str | None,
        Option("--db-path", help="Path to DuckDB index file."),
    ] = None,
) -> None:
    """Show saved schemas for a folder's corpus."""
    console = Console()
    resolved_folder = str(os.path.abspath(folder))
    resolved_db_path = resolve_db_path(db_path)
    storage = DuckDBStorage(resolved_db_path)

    corpus_id = storage.get_corpus_id(resolved_folder)
    if corpus_id is None:
        console.print(
            Panel(
                f"No corpus found for folder: {resolved_folder}\nRun `explore index {resolved_folder}` first.",
                title="⚠️ No Corpus",
                border_style="bold yellow",
            )
        )
        raise Exit(code=1)

    schemas = storage.list_schemas(corpus_id=corpus_id)
    if not schemas:
        console.print(
            Panel(
                f"No schemas saved for corpus: {corpus_id}",
                title="⚠️ No Schemas",
                border_style="bold yellow",
            )
        )
        raise Exit(code=1)

    table = Table(title=f"Schemas for {resolved_folder}")
    table.add_column("Name")
    table.add_column("Active")
    table.add_column("Created At")
    table.add_column("Field Count")

    for schema in schemas:
        table.add_row(
            schema.name,
            "yes" if schema.is_active else "no",
            schema.created_at,
            str(len(schema.schema_def.get("fields", []))),
        )

    console.print(table)
