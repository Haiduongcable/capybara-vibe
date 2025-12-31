"""FastAPI server for configuration UI."""

import asyncio
import socket
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

from capybara.web.routes import router, set_shutdown_callback


def find_free_port(start: int = 8765) -> int:
    """Find available port starting from given port."""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle."""
    yield
    # Cleanup on shutdown


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Capybara Configuration",
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api")

    # Serve static files
    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    async def serve_frontend():
        return FileResponse(static_dir / "index.html")

    return app


async def run_server(open_browser: bool = True) -> None:
    """Run config server and open browser.

    Args:
        open_browser: Whether to auto-open browser (default True)
    """
    port = find_free_port()
    app = create_app()

    # Create shutdown event
    shutdown_event = asyncio.Event()

    def trigger_shutdown():
        shutdown_event.set()

    # Register shutdown callback
    set_shutdown_callback(trigger_shutdown)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    url = f"http://127.0.0.1:{port}"

    # Open browser after short delay
    async def open_browser_task():
        await asyncio.sleep(0.5)
        webbrowser.open(url)

    # Wait for shutdown signal
    async def wait_shutdown():
        await shutdown_event.wait()
        server.should_exit = True

    # Build task list
    tasks = [server.serve(), wait_shutdown()]

    if open_browser:
        tasks.append(open_browser_task())
    else:
        from rich.console import Console

        Console().print(f"[bold]Open in browser:[/bold] {url}")

    await asyncio.gather(*tasks)
