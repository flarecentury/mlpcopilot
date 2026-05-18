"""
FastAPI server for FsExplorer web UI.

Provides a WebSocket endpoint for real-time workflow streaming
and serves the single-page HTML interface.
"""

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .agent import clear_index_context, set_index_context, set_search_flags
from .embeddings import EmbeddingProvider
from .exploration_trace import ExplorationTrace, extract_cited_sources
from .index_config import resolve_db_path
from .indexing import IndexingPipeline
from .indexing.metadata import auto_discover_profile
from .search import IndexedQueryEngine
from .storage import DuckDBStorage
from .workflow import (
    AskHumanEvent,
    GoDeeperEvent,
    HumanAnswerEvent,
    InputEvent,
    ToolCallEvent,
    get_agent,
    reset_agent,
    workflow,
)

app = FastAPI(title="FsExplorer", description="AI-powered filesystem exploration")

_corpus_locks: dict[str, asyncio.Lock] = {}


def _get_corpus_lock(folder: str) -> asyncio.Lock:
    """Return a per-folder asyncio lock, creating one if needed."""
    normalized = str(Path(folder).resolve())
    if normalized not in _corpus_locks:
        _corpus_locks[normalized] = asyncio.Lock()
    return _corpus_locks[normalized]


class TaskRequest(BaseModel):
    """Request model for task submission."""

    task: str
    folder: str = "."
    use_index: bool = False
    db_path: str | None = None


class IndexRequest(BaseModel):
    """Request model for index build/refresh."""

    folder: str = "."
    db_path: str | None = None
    discover_schema: bool = True
    schema_name: str | None = None
    with_metadata: bool = False
    metadata_profile: dict[str, Any] | None = None
    with_embeddings: bool = False


class AutoProfileRequest(BaseModel):
    """Request model for auto-profile generation."""

    folder: str = "."


class SearchRequest(BaseModel):
    """Request model for search queries."""

    corpus_folder: str
    query: str
    filters: str | None = None
    limit: int = 5
    db_path: str | None = None


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    """Serve the main UI HTML file."""
    html_path = Path(__file__).parent / "ui.html"
    if html_path.exists():
        return HTMLResponse(
            content=html_path.read_text(encoding="utf-8"), status_code=200
        )
    return HTMLResponse(content="<h1>UI not found</h1>", status_code=404)


@app.get("/api/folders")
async def list_folders(path: str = "."):
    """
    List folders in the given path.
    Returns list of folder names and current path info.
    """
    try:
        base_path = Path(path).resolve()
        if not base_path.exists():
            return JSONResponse({"error": "Path not found"}, status_code=404)
        if not base_path.is_dir():
            return JSONResponse({"error": "Not a directory"}, status_code=400)

        # Get folders (non-hidden)
        folders = sorted(
            [
                f.name
                for f in base_path.iterdir()
                if f.is_dir() and not f.name.startswith(".")
            ]
        )

        # Get parent path (if not at root)
        parent = str(base_path.parent) if base_path != base_path.parent else None

        return {
            "current": str(base_path),
            "parent": parent,
            "folders": folders,
            "files_count": len([f for f in base_path.iterdir() if f.is_file()]),
        }
    except PermissionError:
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/index/status")
async def index_status(folder: str, db_path: str | None = None):
    """Check whether a folder has been indexed and return status details."""
    try:
        folder_path = Path(folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            return {"indexed": False}

        resolved_db_path = resolve_db_path(db_path)
        if not Path(resolved_db_path).exists():
            return {"indexed": False}

        try:
            storage = DuckDBStorage(resolved_db_path, read_only=True, initialize=False)
        except Exception:
            return {"indexed": False}

        try:
            corpus_id = storage.get_corpus_id(str(folder_path))
            if corpus_id is None:
                storage.close()
                return {"indexed": False}

            docs = storage.list_documents(corpus_id=corpus_id, include_deleted=False)
            active_schema = storage.get_active_schema(corpus_id=corpus_id)
            has_embeddings = storage.has_embeddings(corpus_id=corpus_id)

            schema_name: str | None = None
            has_metadata = False
            schema_fields: list[str] = []
            if active_schema is not None:
                schema_name = active_schema.name
                has_metadata = (
                    active_schema.schema_def.get("metadata_profile") is not None
                )
                fields_def = active_schema.schema_def.get("fields")
                if isinstance(fields_def, list):
                    for f in fields_def:
                        if isinstance(f, dict) and isinstance(f.get("name"), str):
                            schema_fields.append(f["name"])

            storage.close()
            return {
                "indexed": True,
                "corpus_id": corpus_id,
                "document_count": len(docs),
                "schema_name": schema_name,
                "has_metadata": has_metadata,
                "has_embeddings": has_embeddings,
                "schema_fields": schema_fields,
            }
        except Exception:
            storage.close()
            return {"indexed": False}
    except Exception:
        return {"indexed": False}


@app.post("/api/index/auto-profile")
async def generate_auto_profile(request: AutoProfileRequest):
    """Generate an auto-discovered metadata profile for preview/editing."""
    try:
        folder_path = Path(request.folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            return JSONResponse(
                {"error": f"Invalid folder: {request.folder}"}, status_code=400
            )

        profile = await asyncio.to_thread(auto_discover_profile, str(folder_path))
        return {"profile": profile}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/index")
async def build_index(request: IndexRequest):
    """Build or refresh the index for a selected folder."""
    try:
        folder_path = Path(request.folder).resolve()
        if not folder_path.exists():
            return JSONResponse({"error": "Path not found"}, status_code=404)
        if not folder_path.is_dir():
            return JSONResponse({"error": "Not a directory"}, status_code=400)

        lock = _get_corpus_lock(str(folder_path))
        async with lock:
            resolved_db_path = resolve_db_path(request.db_path)
            embedding_provider: EmbeddingProvider | None = None
            if request.with_embeddings:
                try:
                    embedding_provider = EmbeddingProvider()
                except ValueError:
                    embedding_provider = None
            pipeline = IndexingPipeline(
                storage=DuckDBStorage(resolved_db_path),
                embedding_provider=embedding_provider,
            )
            effective_with_metadata = (
                request.with_metadata or request.metadata_profile is not None
            )
            discover_schema = request.discover_schema or effective_with_metadata
            result = pipeline.index_folder(
                str(folder_path),
                discover_schema=discover_schema,
                schema_name=request.schema_name,
                with_metadata=effective_with_metadata,
                metadata_profile=request.metadata_profile,
            )

        return {
            "db_path": resolved_db_path,
            "folder": str(folder_path),
            "corpus_id": result.corpus_id,
            "indexed_files": result.indexed_files,
            "skipped_files": result.skipped_files,
            "deleted_files": result.deleted_files,
            "chunks_written": result.chunks_written,
            "active_documents": result.active_documents,
            "schema_used": result.schema_used,
            "embeddings_written": result.embeddings_written,
            "metadata_mode": "langextract" if effective_with_metadata else "heuristic",
        }
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except PermissionError:
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/search")
async def search_index(request: SearchRequest):
    """Search an indexed corpus and return ranked hits."""
    try:
        folder_path = Path(request.corpus_folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            return JSONResponse(
                {"error": f"Invalid folder: {request.corpus_folder}"}, status_code=400
            )

        resolved_db_path = resolve_db_path(request.db_path)
        storage = DuckDBStorage(resolved_db_path, read_only=True, initialize=False)
        corpus_id = storage.get_corpus_id(str(folder_path))
        if corpus_id is None:
            storage.close()
            return JSONResponse(
                {"error": "No index found for this folder."}, status_code=404
            )

        embedding_provider: EmbeddingProvider | None = None
        if storage.has_embeddings(corpus_id=corpus_id):
            try:
                embedding_provider = EmbeddingProvider()
            except ValueError:
                pass

        engine = IndexedQueryEngine(storage, embedding_provider=embedding_provider)
        hits = engine.search(
            corpus_id=corpus_id,
            query=request.query,
            filters=request.filters,
            limit=request.limit,
        )
        storage.close()

        return {
            "corpus_folder": str(folder_path),
            "query": request.query,
            "hits": [
                {
                    "doc_id": hit.doc_id,
                    "relative_path": hit.relative_path,
                    "absolute_path": hit.absolute_path,
                    "position": hit.position,
                    "text": hit.text,
                    "semantic_score": hit.semantic_score,
                    "metadata_score": hit.metadata_score,
                    "score": hit.score,
                    "matched_by": hit.matched_by,
                }
                for hit in hits
            ],
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.websocket("/ws/explore")
async def websocket_explore(websocket: WebSocket):
    """
    WebSocket endpoint for real-time exploration streaming.

    Protocol:
    1. Client sends: {"task": "user question"}
    2. Server streams events: {"type": "...", "data": {...}}
    3. Final event: {"type": "complete", "data": {...}}
    """
    await websocket.accept()

    try:
        # Receive the task
        data = await websocket.receive_json()
        task = data.get("task", "")
        folder = data.get("folder", ".")
        use_index = bool(data.get("use_index", False))
        db_path = data.get("db_path")
        enable_semantic = bool(data.get("enable_semantic", False))
        enable_metadata = bool(data.get("enable_metadata", False))
        index_storage: DuckDBStorage | None = None

        if not task:
            await websocket.send_json(
                {"type": "error", "data": {"message": "No task provided"}}
            )
            return

        # Validate folder
        folder_path = Path(folder).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            await websocket.send_json(
                {"type": "error", "data": {"message": f"Invalid folder: {folder}"}}
            )
            return

        clear_index_context()
        if use_index:
            resolved_db_path = resolve_db_path(
                db_path if isinstance(db_path, str) else None
            )
            storage = DuckDBStorage(resolved_db_path)
            corpus_id = storage.get_corpus_id(str(folder_path))
            if corpus_id is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {
                            "message": (
                                "No index found for the selected folder. "
                                "Run `explore index <folder>` first."
                            )
                        },
                    }
                )
                return
            index_storage = storage
            set_index_context(str(folder_path), resolved_db_path)

        set_search_flags(
            enable_semantic=enable_semantic and use_index,
            enable_metadata=enable_metadata and use_index,
        )

        trace = ExplorationTrace(root_directory=str(folder_path))

        # Reset agent for fresh state
        reset_agent()

        # Send start event
        await websocket.send_json(
            {
                "type": "start",
                "data": {
                    "task": task,
                    "folder": str(folder_path),
                    "use_index": use_index,
                },
            }
        )

        # Run the workflow
        step_number = 0
        handler = workflow.run(
            start_event=InputEvent(
                task=task,
                folder=str(folder_path),
                use_index=use_index,
                enable_semantic=enable_semantic and use_index,
                enable_metadata=enable_metadata and use_index,
            )
        )

        async for event in handler.stream_events():
            if isinstance(event, ToolCallEvent):
                step_number += 1
                resolved_document_path: str | None = None
                if event.tool_name == "get_document":
                    doc_id = event.tool_input.get("doc_id")
                    if index_storage is not None and isinstance(doc_id, str) and doc_id:
                        document = index_storage.get_document(doc_id=doc_id)
                        if document and not document["is_deleted"]:
                            resolved_document_path = str(document["absolute_path"])
                trace.record_tool_call(
                    step_number=step_number,
                    tool_name=event.tool_name,
                    tool_input=event.tool_input,
                    resolved_document_path=resolved_document_path,
                )
                await websocket.send_json(
                    {
                        "type": "tool_call",
                        "data": {
                            "step": step_number,
                            "tool_name": event.tool_name,
                            "tool_input": event.tool_input,
                            "reason": event.reason,
                        },
                    }
                )

            elif isinstance(event, GoDeeperEvent):
                step_number += 1
                trace.record_go_deeper(
                    step_number=step_number, directory=event.directory
                )
                await websocket.send_json(
                    {
                        "type": "go_deeper",
                        "data": {
                            "step": step_number,
                            "directory": event.directory,
                            "reason": event.reason,
                        },
                    }
                )

            elif isinstance(event, AskHumanEvent):
                step_number += 1
                await websocket.send_json(
                    {
                        "type": "ask_human",
                        "data": {
                            "step": step_number,
                            "question": event.question,
                            "reason": event.reason,
                        },
                    }
                )

                # Wait for human response
                response_data = await websocket.receive_json()
                if response_data.get("type") == "human_response":
                    handler.ctx.send_event(
                        HumanAnswerEvent(response=response_data.get("response", ""))
                    )

        # Get final result
        result = await handler
        cited_sources = extract_cited_sources(result.final_result)

        # Get token usage
        agent = get_agent()
        usage = agent.token_usage
        input_cost, output_cost, total_cost = usage._calculate_cost()

        await websocket.send_json(
            {
                "type": "complete",
                "data": {
                    "final_result": result.final_result,
                    "error": result.error,
                    "stats": {
                        "steps": step_number,
                        "api_calls": usage.api_calls,
                        "documents_scanned": usage.documents_scanned,
                        "documents_parsed": usage.documents_parsed,
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                        "tool_result_chars": usage.tool_result_chars,
                        "estimated_cost": round(total_cost, 6),
                    },
                    "trace": {
                        "step_path": trace.step_path,
                        "referenced_documents": trace.sorted_documents(),
                        "cited_sources": cited_sources,
                    },
                },
            }
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "data": {"message": str(e)}})
    finally:
        set_search_flags(enable_semantic=False, enable_metadata=False)
        clear_index_context()


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
