"""
Aura Backend API

FastAPI server providing:
- LaTeX compilation via local TeX or Docker
- Project management
- Agent chat streaming (PydanticAI)
- YouWare Labs OAuth authentication
"""

import os
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()  # Load .env file before other imports

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
import json

from services.unified_latex import get_unified_latex, UnifiedLatex, CompileResult
from services.project import ProjectService, ProjectInfo
from services.memory import MemoryService
from services.latex_parser import parse_document, parse_bib_file_path, find_unused_citations
from services.docker_setup import get_docker_setup, DockerSetupService, DockerStatus
from agent.providers.openrouter import (
    FreeModelRequiredError,
    FallbackKeyRateLimitError,
    list_free_models,
    get_rate_limit_status,
)
from auth.labs_auth import (
    load_config as load_labs_config,
    build_redirect_uri,
    exchange_code_for_token,
    generate_state,
    sanitize_next_url,
    verify_token_local,
)
from agent.logging import setup_logging, get_logger

# Configure structured logging
# Use JSON output in production (AURA_LOG_JSON=1), colored console in development
log_json = os.getenv("AURA_LOG_JSON", "0") == "1"
log_level = os.getenv("AURA_LOG_LEVEL", "INFO")
setup_logging(json_output=log_json, level=log_level)
logger = get_logger("api")

# Initialize app
app = FastAPI(
    title="Aura Backend API",
    description="Local-first LaTeX IDE with AI agent",
    version="0.1.0"
)

# CORS configuration - use specific origins in production
cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
if cors_origins_env == "*":
    cors_origins = ["*"]
else:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Exception Handlers ============

@app.exception_handler(FreeModelRequiredError)
async def handle_free_model_error(request: Request, exc: FreeModelRequiredError):
    """Handle attempts to use paid models without user's own API key."""
    return JSONResponse(
        status_code=403,
        content={
            "error": "api_key_required",
            "message": str(exc),
            "model_requested": exc.model_id,
            "free_models": list_free_models(),
            "hint": "Set OPENROUTER_API_KEY in Settings to use this model.",
        }
    )


@app.exception_handler(FallbackKeyRateLimitError)
async def handle_rate_limit_error(request: Request, exc: FallbackKeyRateLimitError):
    """Handle rate limit exceeded for free tier users."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "message": str(exc),
            "retry_after": exc.wait_time,
            "rate_limit": get_rate_limit_status(),
            "hint": "Set your own OPENROUTER_API_KEY to remove rate limits.",
        },
        headers={"Retry-After": str(int(exc.wait_time))}
    )


# ============ Auth Configuration ============

labs_config = load_labs_config()
DEV_AUTH_BYPASS = os.getenv("DEV_AUTH_BYPASS", "true").lower() in {"1", "true", "yes", "on"}


def _is_public_api_path(path: str) -> bool:
    """Check if the path is a public API endpoint that doesn't require auth."""
    public_exact = {
        "/api/health",
        "/api/info",
        "/api/free-models",
        "/api/rate-limit",
        "/api/labs/authorize",
        "/api/labs/callback",
        "/api/auth/session",
        "/api/auth/logout",
    }
    public_prefixes = [
        "/api/vibe-research",  # Vibe research endpoints
    ]
    return path in public_exact or any(path.startswith(p) for p in public_prefixes)


@app.middleware("http")
async def labs_auth_middleware(request: Request, call_next):
    """
    YouWare Labs authentication middleware.
    
    Validates JWT tokens from cookies for protected API endpoints.
    In DEV_AUTH_BYPASS mode, all requests are allowed.
    """
    path = request.url.path
    
    # Only apply to /api routes
    if not path.startswith("/api"):
        return await call_next(request)
    
    # Allow OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Allow public endpoints
    if _is_public_api_path(path):
        return await call_next(request)
    
    # Dev bypass mode - skip auth for local development
    if DEV_AUTH_BYPASS:
        request.state.labs_user = {
            "uid": "local-dev",
            "project_id": labs_config.project_id or None,
            "status": "bypass",
        }
        return await call_next(request)
    
    # Check for auth token in cookies
    token = request.cookies.get(labs_config.cookie_name)
    if not token:
        return JSONResponse(
            {"error": "Unauthorized", "detail": "No authentication token"},
            status_code=401
        )
    
    # Verify token
    payload, error = await verify_token_local(labs_config, token)
    if error:
        logger.warning(f"Auth failed: {error}")
        return JSONResponse(
            {"error": "Unauthorized", "detail": error},
            status_code=401
        )
    
    # Attach user info to request state
    request.state.labs_user = payload
    return await call_next(request)


# Initialize services
unified_latex = get_unified_latex()
project_service = ProjectService()


# ============ Health Check ============

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Electron app."""
    return {"status": "ok", "service": "aura-backend"}


@app.get("/api/free-models")
async def get_free_models_list():
    """Get list of available free models (no API key required)."""
    return {
        "models": list_free_models(),
        "default": "meta-llama/llama-3.1-8b-instruct:free",
    }


@app.get("/api/rate-limit")
async def get_rate_limit():
    """Get current rate limit status for free tier."""
    return get_rate_limit_status()


# ============ Auth Endpoints ============

@app.get("/api/auth/session")
async def auth_session(request: Request):
    """
    Check whether the current user is authenticated.
    
    Returns authentication status and user info if authenticated.
    """
    if DEV_AUTH_BYPASS:
        return {
            "authenticated": True,
            "user": {
                "uid": "local-dev",
                "project_id": labs_config.project_id or None,
                "status": "bypass",
            },
        }
    
    token = request.cookies.get(labs_config.cookie_name)
    if not token:
        return JSONResponse({"authenticated": False}, status_code=401)
    
    payload, error = await verify_token_local(labs_config, token)
    if error:
        return JSONResponse({"authenticated": False, "detail": error}, status_code=401)
    
    return {
        "authenticated": True,
        "user": {
            "uid": payload.get("uid"),
            "project_id": payload.get("project_id"),
            "status": payload.get("status"),
        },
    }


@app.post("/api/auth/logout")
async def auth_logout():
    """
    Clear authentication cookie and log out the user.
    """
    response = JSONResponse({"success": True})
    response.delete_cookie(labs_config.cookie_name)
    return response


@app.get("/api/labs/authorize")
async def labs_authorize(request: Request, next: Optional[str] = None):
    """
    Redirect user to YouWare Labs authorization page.
    
    This starts the OAuth flow by redirecting to the Labs server.
    """
    if DEV_AUTH_BYPASS:
        next_url = sanitize_next_url(next)
        response = RedirectResponse(next_url, status_code=302)
        response.set_cookie(
            labs_config.cookie_name,
            "bypass",
            httponly=True,
            secure=labs_config.cookie_secure,
            samesite=labs_config.cookie_samesite,
            max_age=14 * 24 * 60 * 60,
        )
        return response
    
    if not labs_config.project_id:
        raise HTTPException(status_code=500, detail="LABS_PROJECT_ID is not configured")
    
    state = generate_state()
    redirect_uri = build_redirect_uri(labs_config, str(request.base_url))
    next_url = sanitize_next_url(next)
    
    logger.info(
        "Labs authorize: labs_host=%s redirect_uri=%s",
        labs_config.labs_host,
        redirect_uri,
    )
    
    auth_url = f"{labs_config.labs_authorize_url}?{urlencode({
        'project_id': labs_config.project_id,
        'redirect_uri': redirect_uri,
        'state': state,
    })}"
    
    response = RedirectResponse(auth_url, status_code=302)
    
    # Store state and next URL in cookies for verification on callback
    response.set_cookie(
        labs_config.state_cookie_name,
        state,
        httponly=True,
        secure=labs_config.cookie_secure,
        samesite=labs_config.cookie_samesite,
        max_age=600,  # 10 minutes
    )
    response.set_cookie(
        labs_config.next_cookie_name,
        next_url,
        httponly=True,
        secure=labs_config.cookie_secure,
        samesite=labs_config.cookie_samesite,
        max_age=600,
    )
    
    return response


@app.get("/api/labs/callback")
async def labs_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    """
    Handle OAuth callback from YouWare Labs.
    
    Exchanges the authorization code for a JWT token and sets the auth cookie.
    """
    if DEV_AUTH_BYPASS:
        next_url = sanitize_next_url(request.cookies.get(labs_config.next_cookie_name)) or "/"
        response = RedirectResponse(next_url, status_code=302)
        response.set_cookie(
            labs_config.cookie_name,
            "bypass",
            httponly=True,
            secure=labs_config.cookie_secure,
            samesite=labs_config.cookie_samesite,
            max_age=14 * 24 * 60 * 60,
        )
        response.delete_cookie(labs_config.state_cookie_name)
        response.delete_cookie(labs_config.next_cookie_name)
        return response
    
    if not labs_config.project_id:
        raise HTTPException(status_code=500, detail="LABS_PROJECT_ID is not configured")
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    
    saved_state = request.cookies.get(labs_config.state_cookie_name)
    next_url = sanitize_next_url(request.cookies.get(labs_config.next_cookie_name)) or "/"
    
    # Verify state if present (CSRF protection)
    if saved_state and state != saved_state:
        raise HTTPException(status_code=400, detail="State mismatch - possible CSRF attack")
    
    # Exchange code for token
    try:
        redirect_uri = build_redirect_uri(labs_config, str(request.base_url))
        token = await exchange_code_for_token(labs_config, code, redirect_uri)
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to exchange authorization code")
    
    # Set auth cookie and redirect
    response = RedirectResponse(next_url, status_code=302)
    response.set_cookie(
        labs_config.cookie_name,
        token,
        httponly=True,
        secure=labs_config.cookie_secure,
        samesite=labs_config.cookie_samesite,
        max_age=14 * 24 * 60 * 60,  # 14 days
    )
    
    # Clean up OAuth cookies
    response.delete_cookie(labs_config.state_cookie_name)
    response.delete_cookie(labs_config.next_cookie_name)
    
    return response


@app.get("/api/info")
async def get_info():
    """Get information about the Aura backend."""
    from agent.subagents import list_subagents

    latex_status = unified_latex.get_status()

    return {
        "name": "Aura Backend",
        "version": "0.1.0",
        "description": "Local-first LaTeX IDE with AI agent",
        "latex_available": unified_latex.is_available(),
        "latex_backend": latex_status["active_backend"],
        "latex_status": latex_status,
        "subagents": [s["name"] for s in list_subagents()],
        "features": {
            "compilation": True,
            "streaming": True,
            "hitl": True,
            "planning": True,
            "steering": True,
            "compression": True,
        },
    }


# ============ Request/Response Models ============

class CompileRequest(BaseModel):
    project_path: str
    filename: str = "main.tex"


class CompileResponse(BaseModel):
    success: bool
    pdf_path: Optional[str] = None
    error_summary: str = ""
    log_output: str = ""
    tex_not_available: bool = False  # True if no LaTeX compiler is available


class CreateProjectRequest(BaseModel):
    name: str
    path: Optional[str] = None  # Custom path, if None uses ~/aura-projects/
    template: Optional[str] = None  # If None, creates empty project


class FileReadRequest(BaseModel):
    project_path: str
    filename: str


class FileWriteRequest(BaseModel):
    project_path: str
    filename: str
    content: str


class FileDeleteRequest(BaseModel):
    project_path: str
    filename: str


class FileRenameRequest(BaseModel):
    project_path: str
    old_filename: str
    new_filename: str


class FileCopyRequest(BaseModel):
    project_path: str
    source_filename: str
    dest_filename: str


class FileListRequest(BaseModel):
    project_path: str


class SyncTexRequest(BaseModel):
    """Request for SyncTeX PDF-to-source lookup."""
    project_path: str
    pdf_file: str
    page: int
    x: float
    y: float
    clicked_word: Optional[str] = None  # Word selected by double-click for precise matching


class ProviderConfig(BaseModel):
    """Provider configuration for model selection."""
    name: str = "openrouter"  # "openrouter" or "dashscope"
    model: Optional[str] = None  # Model ID for dashscope (e.g., "deepseek-v3.2")
    api_key: Optional[str] = None  # API key for dashscope


class ChatRequest(BaseModel):
    message: str
    project_path: str
    history: Optional[list] = None
    session_id: Optional[str] = None  # Optional session ID for persistence
    provider: Optional[ProviderConfig] = None  # Optional provider config


# ============ Memory Models ============

class MemoryEntryRequest(BaseModel):
    project_path: str


class AddPaperRequest(BaseModel):
    project_path: str
    title: str
    authors: list[str]
    arxiv_id: str = ""
    summary: str = ""
    tags: list[str] = []


class AddCitationRequest(BaseModel):
    project_path: str
    bibtex_key: str
    reason: str
    paper_id: Optional[str] = None


class AddConventionRequest(BaseModel):
    project_path: str
    rule: str
    example: str = ""


class AddTodoRequest(BaseModel):
    project_path: str
    task: str
    priority: str = "medium"
    status: str = "pending"


class AddNoteRequest(BaseModel):
    project_path: str
    content: str
    tags: list[str] = []


class UpdateEntryRequest(BaseModel):
    project_path: str
    data: dict


# ============ Vibe Research Models ============

class VibeResearchStartRequest(BaseModel):
    project_path: str
    topic: str
    max_papers: int = 100
    max_papers_to_read: int = 30
    target_hypotheses: int = 5
    provider: Optional[ProviderConfig] = None


class VibeResearchRunRequest(BaseModel):
    project_path: str
    provider: Optional[ProviderConfig] = None


class VibeResearchSessionRequest(BaseModel):
    project_path: str


class VerifyReferencesRequest(BaseModel):
    project_path: str
    bib_file: Optional[str] = None


class ApproveReferenceRequest(BaseModel):
    project_path: str
    cite_key: str


# ============ Health Check ============

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Aura Backend",
        "version": "0.1.0",
        "latex_available": unified_latex.is_available(),
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "latex": unified_latex.is_available(),
        "latex_backend": unified_latex.get_status()["active_backend"],
    }


# ============ Compilation Endpoints ============

@app.post("/api/compile", response_model=CompileResponse)
async def compile_latex(request: CompileRequest):
    """
    Compile a LaTeX project to PDF.

    Uses local TeX if available, falls back to Docker.
    """
    logger.info(f"Compiling {request.filename} in {request.project_path}")

    result: CompileResult = await unified_latex.compile(
        project_path=request.project_path,
        main_file=request.filename,
    )

    return CompileResponse(
        success=result.success,
        pdf_path=result.pdf_path,
        error_summary=result.error_summary or "",
        log_output=result.log[-5000:] if result.log else "",  # Limit log size
        tex_not_available=result.tex_not_available,
    )


@app.post("/api/check-syntax", response_model=CompileResponse)
async def check_syntax(request: CompileRequest):
    """
    Quick syntax check without full compilation.
    """
    result = await unified_latex.check_syntax(
        project_path=request.project_path,
        main_file=request.filename,
    )

    return CompileResponse(
        success=result.success,
        error_summary=result.error_summary or "",
        log_output=result.log[-2000:] if result.log else "",
    )


@app.post("/api/synctex/view")
async def synctex_view(request: SyncTexRequest):
    """
    Query SyncTeX to find source location for a PDF position.

    Used for PDF-to-source navigation (double-click on PDF jumps to source).
    """
    from services.synctex import get_synctex_service
    from pathlib import Path

    synctex = get_synctex_service()
    result = await synctex.view(
        project_path=request.project_path,
        pdf_file=request.pdf_file,
        page=request.page,
        x=request.x,
        y=request.y,
    )

    # If we have a clicked word, try to find its exact position in the source line
    column = result.column
    if result.success and request.clicked_word and result.file and result.line:
        try:
            # Read the source file to find the word
            source_path = Path(request.project_path) / result.file
            if source_path.exists():
                with open(source_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                    if 0 < result.line <= len(lines):
                        line_content = lines[result.line - 1]
                        # Find the clicked word in the line (case-sensitive)
                        word = request.clicked_word.strip()
                        if word:
                            pos = line_content.find(word)
                            if pos >= 0:
                                # Column is 1-indexed
                                column = pos + 1
        except Exception as e:
            # If we can't read the file, fall back to estimated column
            pass

    return {
        "success": result.success,
        "file": result.file,
        "line": result.line,
        "column": column,
        "error": result.error,
    }


@app.get("/api/pdf/{project_name}")
async def get_pdf(project_name: str, filename: str = "main.pdf"):
    """
    Serve the compiled PDF file from ~/aura-projects/.
    """
    from services.project import PROJECTS_DIR

    pdf_path = PROJECTS_DIR / project_name / filename

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


# ============ Docker Setup Endpoints ============

docker_setup = get_docker_setup()


@app.get("/api/docker/status")
async def get_docker_status():
    """
    Get Docker installation status.
    Returns: status, docker_installed, docker_running, image_pulled
    """
    status = docker_setup.get_status()
    return {
        "status": status.status.value,
        "docker_installed": status.docker_installed,
        "docker_running": status.docker_running,
        "image_pulled": status.image_pulled,
        "image_name": status.image_name,
        "download_progress": status.download_progress,
        "download_path": status.download_path,
        "error": status.error,
    }


@app.post("/api/docker/download")
async def download_docker():
    """
    Download Docker.dmg to Downloads folder.
    """
    status = await docker_setup.download_docker()
    return {
        "status": status.status.value,
        "download_progress": status.download_progress,
        "download_path": status.download_path,
        "error": status.error,
    }


@app.post("/api/docker/open-installer")
async def open_docker_installer():
    """
    Open the Docker.dmg installer.
    """
    status = await docker_setup.open_installer()
    return {
        "status": status.status.value,
        "download_path": status.download_path,
        "error": status.error,
    }


@app.post("/api/docker/start")
async def start_docker():
    """
    Start Docker Desktop application.
    """
    status = await docker_setup.start_docker()
    return {
        "status": status.status.value,
        "docker_installed": status.docker_installed,
        "docker_running": status.docker_running,
        "error": status.error,
    }


@app.post("/api/docker/pull-image")
async def pull_docker_image():
    """
    Pull/build the TeX Docker image.
    """
    status = await docker_setup.pull_image()
    return {
        "status": status.status.value,
        "docker_running": status.docker_running,
        "image_pulled": status.image_pulled,
        "error": status.error,
    }


class PdfRequest(BaseModel):
    project_path: str
    filename: str = "main.pdf"


@app.post("/api/pdf/serve")
async def serve_pdf(request: PdfRequest):
    """
    Serve a PDF file from any project path.
    """
    from pathlib import Path

    pdf_path = Path(request.project_path) / request.filename

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found: {request.filename}")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=request.filename,
    )


# ============ Project Endpoints ============

@app.get("/api/projects")
async def list_projects() -> list[dict]:
    """List all projects."""
    projects = project_service.list_all()
    return [
        {
            "name": p.name,
            "path": p.path,
            "has_overleaf": p.has_overleaf,
            "last_modified": p.last_modified,
        }
        for p in projects
    ]


@app.post("/api/projects")
async def create_project(request: CreateProjectRequest) -> dict:
    """Create a new project."""
    try:
        project = project_service.create(
            name=request.name,
            path=request.path,
            template=request.template,
        )
        return {
            "name": project.name,
            "path": project.path,
            "has_overleaf": project.has_overleaf,
            "last_modified": project.last_modified,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/projects/{project_name}/files")
async def get_project_files(project_name: str) -> list[dict]:
    """Get file tree for a project."""
    from services.project import PROJECTS_DIR

    project_path = PROJECTS_DIR / project_name
    if not project_path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    return project_service.get_files(str(project_path))


@app.post("/api/files/read")
async def read_file(request: FileReadRequest) -> dict:
    """Read a file from a project."""
    try:
        content = project_service.read_file(request.project_path, request.filename)
        return {"content": content}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/files/write")
async def write_file(request: FileWriteRequest) -> dict:
    """Write to a file in a project."""
    project_service.write_file(
        request.project_path,
        request.filename,
        request.content,
    )
    return {"success": True}


@app.post("/api/files/delete")
async def delete_file(request: FileDeleteRequest) -> dict:
    """Delete a file from a project."""
    from pathlib import Path

    project_path = Path(request.project_path)
    file_path = project_path / request.filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.filename}")

    # Safety check: ensure file is within project directory
    try:
        file_path.resolve().relative_to(project_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    if file_path.is_dir():
        import shutil
        shutil.rmtree(file_path)
    else:
        file_path.unlink()

    return {"success": True}


@app.post("/api/files/rename")
async def rename_file(request: FileRenameRequest) -> dict:
    """Rename a file in a project."""
    from pathlib import Path

    project_path = Path(request.project_path)
    old_path = project_path / request.old_filename
    new_path = project_path / request.new_filename

    if not old_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.old_filename}")

    if new_path.exists():
        raise HTTPException(status_code=400, detail=f"File already exists: {request.new_filename}")

    # Safety check: ensure both paths are within project directory
    try:
        old_path.resolve().relative_to(project_path.resolve())
        new_path.resolve().relative_to(project_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Create parent directory if needed
    new_path.parent.mkdir(parents=True, exist_ok=True)

    old_path.rename(new_path)

    return {"success": True, "new_path": str(new_path.relative_to(project_path))}


@app.post("/api/files/copy")
async def copy_file(request: FileCopyRequest) -> dict:
    """Copy a file or directory in a project."""
    from pathlib import Path
    import shutil

    project_path = Path(request.project_path)
    source_path = project_path / request.source_filename
    dest_path = project_path / request.dest_filename

    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Source not found: {request.source_filename}")

    if dest_path.exists():
        raise HTTPException(status_code=400, detail=f"Destination already exists: {request.dest_filename}")

    # Safety check: ensure both paths are within project directory
    try:
        source_path.resolve().relative_to(project_path.resolve())
        dest_path.resolve().relative_to(project_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Create parent directory if needed
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if source_path.is_dir():
        shutil.copytree(source_path, dest_path)
    else:
        shutil.copy2(source_path, dest_path)

    return {"success": True, "new_path": str(dest_path.relative_to(project_path))}


@app.post("/api/files/list")
async def list_files(request: FileListRequest) -> list[dict]:
    """
    List files in a project directory.

    Works with any directory path, not just projects in ~/aura-projects/.
    """
    from pathlib import Path

    project_path = Path(request.project_path)
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.project_path}")

    return project_service.get_files(str(project_path))


# ============ Agent Chat Endpoints ============

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream agent responses via Server-Sent Events.

    The agent will process the message and may use tools to help
    with LaTeX editing, compilation, and research.

    Uses PydanticAI-based agent with streaming support.
    """
    from agent.streaming import stream_agent_sse

    # Use session_id from request, or fall back to "default"
    session_id = request.session_id or "default"

    # Extract provider config
    provider_config = None
    if request.provider:
        provider_config = {
            "name": request.provider.name,
            "model": request.provider.model,
            "api_key": request.provider.api_key,
        }

    # Handle /research command - route through main agent with delegate_to_subagent
    # Check for both raw command and transformed message from frontend
    message = request.message.strip()
    research_query = None

    if message.lower().startswith("/research"):
        research_query = message[9:].strip()
    elif message.lower().startswith("search for academic papers about:"):
        research_query = message[33:].strip()
    elif message.lower().startswith("search for academic papers about"):
        research_query = message[32:].strip()

    # Transform /research into a delegate_to_subagent call through main agent
    if research_query is not None:
        # Route through main agent so it goes through proper streaming with HITL
        # Instruct agent to pass through results without summarizing
        message = f'''Use the research subagent to search for: {research_query or "academic papers"}

IMPORTANT: After getting the research results, output the COMPLETE subagent result including ALL paper links. Do not summarize or omit the links section.'''

    async def event_generator():
        try:
            async for sse_data in stream_agent_sse(
                message=message,  # Use the (possibly transformed) message
                project_path=request.project_path,
                message_history=request.history,
                session_id=session_id,
                provider_config=provider_config,
            ):
                # SSE data is already formatted as "data: {...}\n\n"
                # Parse it to get event type and content
                if sse_data.startswith("data: "):
                    data = json.loads(sse_data[6:].strip())
                    yield {
                        "event": data.get("type", "message"),
                        "data": json.dumps(data),
                    }
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": str(e)}),
            }

    return EventSourceResponse(event_generator())


async def _handle_research_command(query: str, project_path: str, session_id: str):
    """
    Handle /research command with HITL for domain/venue preferences.
    Uses the research agent to search and synthesize results.
    """
    import asyncio
    from agent.subagents.research import ResearchAgent, ResearchMode
    from agent.venue_hitl import get_research_preference_manager

    event_queue: asyncio.Queue = asyncio.Queue()

    async def event_generator():
        try:
            # Set up HITL callbacks for domain/venue preferences
            pref_manager = get_research_preference_manager()

            async def on_domain_preference_request(request):
                await event_queue.put({
                    "event": "domain_preference_request",
                    "data": json.dumps({
                        "type": "domain_preference_request",
                        "request_id": request.request_id,
                        "topic": request.topic,
                        "suggested_domain": request.suggested_domain,
                    }),
                })

            async def on_venue_preference_request(request):
                await event_queue.put({
                    "event": "venue_preference_request",
                    "data": json.dumps({
                        "type": "venue_preference_request",
                        "request_id": request.request_id,
                        "topic": request.topic,
                        "domain": request.domain,
                        "suggested_venues": request.suggested_venues,
                    }),
                })

            pref_manager.set_domain_event_callback(on_domain_preference_request)
            pref_manager.set_venue_event_callback(on_venue_preference_request)

            # Request research preferences through HITL
            # This emits events and waits for user responses
            async def get_preferences():
                return await pref_manager.request_research_preferences(
                    topic=query,
                    session_id=session_id,
                )

            # Start preference request in background
            pref_task = asyncio.create_task(get_preferences())

            # Yield events while waiting for preferences
            while not pref_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    continue

            # Get the preferences result
            prefs = await pref_task

            # Create research agent in CHAT mode
            agent = ResearchAgent()
            agent.mode = ResearchMode.CHAT

            # Run the search with preferences
            result = await agent.run(
                task=query or "academic papers",
                context={
                    "mode": "chat",
                    "project_path": project_path,
                    "domain": prefs.domain,
                    "venue_filter": prefs.venues,
                    "venue_preferences_asked": True,
                },
            )

            # Stream the output as text deltas to match SSE format
            output = result.output or ""
            if result.success:
                # Send output in chunks to simulate streaming
                chunk_size = 100
                for i in range(0, len(output), chunk_size):
                    chunk = output[i:i + chunk_size]
                    yield {
                        "event": "text_delta",
                        "data": json.dumps({"type": "text_delta", "content": chunk}),
                    }

                # Send done event
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "type": "done",
                        "output": output,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    }),
                }
            else:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "type": "error",
                        "message": result.error or "Research failed",
                    }),
                }

        except Exception as e:
            logger.error(f"Research command error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": str(e)}),
            }

    return EventSourceResponse(event_generator())


@app.post("/api/chat/simple")
async def chat_simple(request: ChatRequest) -> dict:
    """
    Simple non-streaming chat endpoint.

    Returns the complete response after agent finishes.
    Uses PydanticAI-based agent.
    """
    from agent.streaming import run_agent

    # Use session_id from request, or fall back to "default"
    session_id = request.session_id or "default"

    try:
        result = await run_agent(
            message=request.message,
            project_path=request.project_path,
            message_history=request.history,
            session_id=session_id,
        )
        return {
            "response": result["output"],
            "usage": result["usage"],
        }
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ClearChatRequest(BaseModel):
    project_path: str


class CreateChatSessionRequest(BaseModel):
    project_path: str
    name: Optional[str] = None  # Optional session name, auto-generated if not provided


class RenameChatSessionRequest(BaseModel):
    project_path: str
    name: str


@app.post("/api/chat/clear")
async def clear_chat_history(request: ClearChatRequest) -> dict:
    """
    Clear conversation history for a project.

    Use this to start a fresh conversation.
    """
    from agent.streaming import clear_session_history

    session_id = request.project_path or "default"
    clear_session_history(session_id)

    return {
        "success": True,
        "message": f"Cleared chat history for session: {session_id}",
    }


# ============ Chat Session CRUD Endpoints ============

@app.post("/api/chat/sessions/create")
async def create_chat_session(request: CreateChatSessionRequest) -> dict:
    """
    Create a new chat session.

    Returns the created session info.
    """
    from agent.streaming import ChatSession

    session = ChatSession(
        project_path=request.project_path,
        name=request.name or "",
    )
    # Initialize with empty messages and save
    session.messages = []
    session.message_count = 0
    session.save()

    return session.to_summary()


@app.get("/api/chat/sessions")
async def list_chat_sessions(project_path: str) -> dict:
    """
    List all chat sessions for a project.

    Returns sessions sorted by updated_at (newest first).
    """
    from agent.streaming import ChatSession

    sessions = ChatSession.list_sessions(project_path)

    return {
        "count": len(sessions),
        "sessions": sessions,
    }


@app.get("/api/chat/session/{session_id}")
async def get_chat_session(session_id: str, project_path: str) -> dict:
    """
    Get a chat session with its messages.

    Returns the session info and message history.
    """
    from agent.streaming import ChatSession

    session = ChatSession.load(project_path, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    # Convert messages to UI-friendly format
    ui_messages = []
    for msg in session.messages:
        msg_type = msg.get("type", "")
        if msg_type == "ModelRequest":
            for part in msg.get("parts", []):
                if part.get("type") == "user_prompt":
                    ui_messages.append({
                        "role": "user",
                        "content": part.get("content", ""),
                    })
        elif msg_type == "ModelResponse":
            content_parts = []
            for part in msg.get("parts", []):
                if part.get("type") == "text":
                    content_parts.append(part.get("content", ""))
            if content_parts:
                ui_messages.append({
                    "role": "assistant",
                    "content": "\n".join(content_parts),
                })

    return {
        **session.to_summary(),
        "messages": ui_messages,
    }


@app.delete("/api/chat/session/{session_id}")
async def delete_chat_session(session_id: str, project_path: str) -> dict:
    """
    Delete a chat session.
    """
    from agent.streaming import ChatSession

    success = ChatSession.delete(project_path, session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {
        "success": True,
        "message": f"Deleted session: {session_id}",
    }


@app.put("/api/chat/session/{session_id}/rename")
async def rename_chat_session(session_id: str, request: RenameChatSessionRequest) -> dict:
    """
    Rename a chat session.
    """
    from agent.streaming import ChatSession

    session = ChatSession.load(request.project_path, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    session.name = request.name
    session.project_path = request.project_path
    session.save()

    return session.to_summary()


@app.get("/api/tools")
async def list_tools() -> list[dict]:
    """List all available agent tools."""
    from agent.pydantic_agent import aura_agent

    # Get tool definitions from PydanticAI agent
    tools = []
    toolset = aura_agent._function_toolset
    if toolset and hasattr(toolset, '_tools'):
        for name, tool in toolset._tools.items():
            tools.append({
                "name": name,
                "description": tool.description or "",
            })
    return tools


# ============ Compression Endpoints ============

class CompressionStatsRequest(BaseModel):
    history: list


@app.post("/api/compression/stats")
async def get_compression_stats(request: CompressionStatsRequest) -> dict:
    """
    Get compression statistics for a message history.

    Returns token estimates and whether compression would be triggered.
    """
    from agent.compression import get_compressor

    compressor = get_compressor()
    return compressor.get_compression_stats(request.history)


@app.post("/api/compression/compress")
async def compress_history(request: CompressionStatsRequest) -> dict:
    """
    Manually compress a message history.

    Returns the compressed history and statistics.
    """
    from agent.compression import get_compressor

    compressor = get_compressor()
    stats_before = compressor.get_compression_stats(request.history)

    if not compressor.should_compress(request.history):
        return {
            "compressed": False,
            "reason": "History does not meet compression threshold",
            "stats": stats_before,
        }

    try:
        compressed = await compressor.compress(request.history)
        stats_after = compressor.get_compression_stats(compressed)

        return {
            "compressed": True,
            "original_messages": len(request.history),
            "compressed_messages": len(compressed),
            "tokens_before": stats_before["estimated_tokens"],
            "tokens_after": stats_after["estimated_tokens"],
            "tokens_saved": stats_before["estimated_tokens"] - stats_after["estimated_tokens"],
            "history": compressed,
        }
    except Exception as e:
        logger.error(f"Compression error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ HITL (Human-in-the-Loop) Endpoints ============

class HITLApproveRequest(BaseModel):
    request_id: str
    modified_args: Optional[dict] = None


class HITLRejectRequest(BaseModel):
    request_id: str
    reason: str = "User rejected"


@app.get("/api/hitl/pending")
async def get_pending_approvals() -> list[dict]:
    """
    Get all pending HITL approval requests.

    Returns list of pending requests that need user approval.
    """
    from agent.hitl import get_hitl_manager

    manager = get_hitl_manager()
    pending = await manager.get_pending()

    return [req.to_dict() for req in pending]


@app.get("/api/hitl/request/{request_id}")
async def get_approval_request(request_id: str) -> dict:
    """
    Get a specific approval request by ID.
    """
    from agent.hitl import get_hitl_manager

    manager = get_hitl_manager()
    request = await manager.get_request(request_id)

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    return request.to_dict()


@app.post("/api/hitl/approve")
async def approve_request(request: HITLApproveRequest) -> dict:
    """
    Approve a pending HITL request.

    The tool will continue execution after approval.
    Optionally provide modified_args to change the tool arguments.
    """
    from agent.hitl import get_hitl_manager

    manager = get_hitl_manager()
    success = await manager.approve(
        request_id=request.request_id,
        modified_args=request.modified_args,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Request not found or already resolved"
        )

    return {
        "success": True,
        "request_id": request.request_id,
        "status": "approved" if not request.modified_args else "modified",
    }


@app.post("/api/hitl/reject")
async def reject_request(request: HITLRejectRequest) -> dict:
    """
    Reject a pending HITL request.

    The tool will return a rejection message to the agent.
    """
    from agent.hitl import get_hitl_manager

    manager = get_hitl_manager()
    success = await manager.reject(
        request_id=request.request_id,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Request not found or already resolved"
        )

    return {
        "success": True,
        "request_id": request.request_id,
        "status": "rejected",
        "reason": request.reason,
    }


@app.get("/api/hitl/config")
async def get_hitl_config() -> dict:
    """
    Get the current HITL configuration.

    Shows which tools require approval.
    """
    from agent.hitl import get_hitl_manager

    manager = get_hitl_manager()

    return {
        "approval_required": list(manager.config.approval_required),
        "preview_only": list(manager.config.preview_only),
        "approval_timeout": manager.config.approval_timeout,
        "auto_approve_on_timeout": manager.config.auto_approve_on_timeout,
    }


# ============ HITL Async (Non-blocking) Endpoints ============

class HITLBatchApproveRequest(BaseModel):
    operation_ids: list[str]


class HITLBatchRejectRequest(BaseModel):
    operation_ids: list[str]
    reason: str = "User rejected"


class HITLExecuteRequest(BaseModel):
    operation_id: str
    project_path: str


class HITLBatchExecuteRequest(BaseModel):
    operation_ids: list[str]
    project_path: str


@app.websocket("/ws/hitl/{session_id}")
async def hitl_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time HITL notifications.

    Connect to receive notifications about:
    - New pending operations
    - Status changes (approved/rejected)
    - Execution results

    Message format:
    {
        "type": "pending" | "status" | "result",
        "data": { ... }
    }
    """
    from agent.hitl_ws import get_hitl_ws_manager

    manager = get_hitl_ws_manager()
    await manager.connect(websocket, session_id)

    try:
        while True:
            # Keep connection alive by receiving pings
            data = await websocket.receive_text()
            # Could handle client messages here if needed
    except WebSocketDisconnect:
        await manager.disconnect(websocket, session_id)


@app.get("/api/hitl/v2/pending")
async def get_pending_operations_v2(session_id: str) -> list[dict]:
    """
    Get all pending operations for a session (async HITL v2).

    Uses the new HITLStore instead of the blocking HITLManager.
    Returns operations with diff preview data.
    """
    from agent.hitl_store import get_hitl_store

    store = get_hitl_store()
    pending = await store.get_pending_by_session(session_id)

    return [op.to_dict() for op in pending]


@app.get("/api/hitl/v2/operation/{operation_id}")
async def get_operation_v2(operation_id: str) -> dict:
    """
    Get a specific operation by ID (async HITL v2).
    """
    from agent.hitl_store import get_hitl_store

    store = get_hitl_store()
    operation = await store.get_operation(operation_id)

    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    return operation.to_dict()


@app.post("/api/hitl/v2/approve")
async def approve_operation_v2(request: HITLApproveRequest) -> dict:
    """
    Approve a pending operation (async HITL v2).

    After approval, call /api/hitl/v2/execute to execute the operation.
    """
    from agent.hitl_store import get_hitl_store

    store = get_hitl_store()
    success = await store.approve(
        request.request_id,
        modified_args=request.modified_args,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Operation not found, not pending, or expired"
        )

    return {
        "success": True,
        "operation_id": request.request_id,
        "status": "approved",
    }


@app.post("/api/hitl/v2/reject")
async def reject_operation_v2(request: HITLRejectRequest) -> dict:
    """
    Reject a pending operation (async HITL v2).
    """
    from agent.hitl_store import get_hitl_store

    store = get_hitl_store()
    success = await store.reject(
        request.request_id,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Operation not found or not pending"
        )

    return {
        "success": True,
        "operation_id": request.request_id,
        "status": "rejected",
    }


@app.post("/api/hitl/v2/batch-approve")
async def batch_approve_operations_v2(request: HITLBatchApproveRequest) -> dict:
    """
    Approve multiple operations at once (async HITL v2).

    Returns results for each operation.
    """
    from agent.hitl_store import get_hitl_store

    store = get_hitl_store()
    results = await store.batch_approve(request.operation_ids)

    return {
        "success": all(results.values()),
        "results": results,
        "approved": sum(1 for v in results.values() if v),
        "failed": sum(1 for v in results.values() if not v),
    }


@app.post("/api/hitl/v2/batch-reject")
async def batch_reject_operations_v2(request: HITLBatchRejectRequest) -> dict:
    """
    Reject multiple operations at once (async HITL v2).
    """
    from agent.hitl_store import get_hitl_store

    store = get_hitl_store()
    results = await store.batch_reject(
        request.operation_ids,
        reason=request.reason,
    )

    return {
        "success": all(results.values()),
        "results": results,
        "rejected": sum(1 for v in results.values() if v),
        "failed": sum(1 for v in results.values() if not v),
    }


@app.post("/api/hitl/v2/execute")
async def execute_operation_v2(request: HITLExecuteRequest) -> dict:
    """
    Execute an approved operation (async HITL v2).

    The operation must be in APPROVED status.
    """
    from agent.hitl_executor import get_hitl_executor

    executor = get_hitl_executor()

    try:
        result = await executor.execute_operation(
            request.operation_id,
            request.project_path,
        )
        return {
            "success": True,
            "operation_id": request.operation_id,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hitl/v2/batch-execute")
async def batch_execute_operations_v2(request: HITLBatchExecuteRequest) -> dict:
    """
    Execute multiple approved operations (async HITL v2).
    """
    from agent.hitl_executor import get_hitl_executor

    executor = get_hitl_executor()
    results = await executor.execute_batch(
        request.operation_ids,
        request.project_path,
    )

    success_count = sum(1 for r in results.values() if r.get("success"))
    fail_count = len(results) - success_count

    return {
        "success": fail_count == 0,
        "results": results,
        "executed": success_count,
        "failed": fail_count,
    }


# ============ Research Preference HITL Endpoints ============

class DomainPreferenceSubmitRequest(BaseModel):
    request_id: str
    domain: str


class VenuePreferenceSubmitRequest(BaseModel):
    request_id: str
    venues: list[str] = []


@app.post("/api/domain-preferences/submit")
async def submit_domain_preferences(request: DomainPreferenceSubmitRequest) -> dict:
    """
    Submit domain preference for a pending research request.

    Called by the frontend when user submits the domain preference modal.
    """
    from agent.venue_hitl import get_research_preference_manager

    manager = get_research_preference_manager()
    success = await manager.submit_domain_preference(
        request_id=request.request_id,
        domain=request.domain,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Request not found or already resolved"
        )

    return {
        "success": True,
        "request_id": request.request_id,
        "domain": request.domain,
    }


@app.post("/api/venue-preferences/submit")
async def submit_venue_preferences(request: VenuePreferenceSubmitRequest) -> dict:
    """
    Submit venue preferences for a pending research request.

    Called by the frontend when user submits the venue preference modal.
    """
    from agent.venue_hitl import get_research_preference_manager

    manager = get_research_preference_manager()
    success = await manager.submit_venue_preferences(
        request_id=request.request_id,
        venues=request.venues,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Request not found or already resolved"
        )

    return {
        "success": True,
        "request_id": request.request_id,
        "venues": request.venues,
    }


@app.get("/api/domain-preferences/pending")
async def get_pending_domain_preferences(session_id: Optional[str] = None) -> dict:
    """
    Get pending domain preference requests.
    """
    from agent.venue_hitl import get_research_preference_manager

    manager = get_research_preference_manager()
    pending = await manager.get_pending_domain(session_id)

    return {
        "pending": [req.to_dict() for req in pending],
    }


@app.get("/api/venue-preferences/pending")
async def get_pending_venue_preferences(session_id: Optional[str] = None) -> dict:
    """
    Get pending venue preference requests.
    """
    from agent.venue_hitl import get_research_preference_manager

    manager = get_research_preference_manager()
    pending = await manager.get_pending_venue(session_id)

    return {
        "pending": [req.to_dict() for req in pending],
    }


# ============ Steering Endpoints ============

class SteeringAddRequest(BaseModel):
    content: str
    priority: int = 0
    session_id: Optional[str] = None


@app.post("/api/steering/add")
async def add_steering(request: SteeringAddRequest) -> dict:
    """
    Add a steering message to guide the agent.

    Steering messages are injected into the next agent request
    to redirect or guide the agent's behavior.

    Priority levels:
        0 - Normal (default)
        1 - High (processed before normal)
        2 - Urgent (should interrupt if possible)
    """
    from agent.steering import get_steering_manager

    manager = get_steering_manager()
    message = await manager.add(
        content=request.content,
        priority=request.priority,
        session_id=request.session_id,
    )

    return {
        "success": True,
        "message_id": message.message_id,
        "priority": message.priority,
        "queue_size": manager.queue_size(),
    }


@app.get("/api/steering/pending")
async def get_pending_steering(session_id: Optional[str] = None) -> dict:
    """
    Get pending steering messages without removing them.

    Useful for UI to display what steering is queued.
    """
    from agent.steering import get_steering_manager

    manager = get_steering_manager()
    messages = await manager.peek(session_id=session_id)

    return {
        "count": len(messages),
        "messages": [msg.to_dict() for msg in messages],
    }


@app.delete("/api/steering/clear")
async def clear_steering(session_id: Optional[str] = None) -> dict:
    """
    Clear all pending steering messages.

    Optionally filter by session_id to clear only for a specific session.
    """
    from agent.steering import get_steering_manager

    manager = get_steering_manager()
    cleared = await manager.clear(session_id=session_id)

    return {
        "success": True,
        "cleared_count": cleared,
    }


@app.get("/api/steering/config")
async def get_steering_config() -> dict:
    """
    Get the current steering configuration.
    """
    from agent.steering import get_steering_manager

    manager = get_steering_manager()

    return {
        "max_queue_size": manager.config.max_queue_size,
        "default_priority": manager.config.default_priority,
        "combine_messages": manager.config.combine_messages,
        "current_queue_size": manager.queue_size(),
    }


# ============ Subagent Endpoints ============

class SubagentRunRequest(BaseModel):
    subagent: str
    task: str
    project_path: Optional[str] = None


@app.get("/api/subagents")
async def get_available_subagents() -> list[dict]:
    """
    List all available subagents.

    Returns a list of subagents with their names and descriptions.
    """
    from agent.subagents import list_subagents

    return list_subagents()


@app.get("/api/providers/dashscope/models")
async def get_dashscope_models() -> list[dict]:
    """
    List available models for DashScope provider.

    Returns a list of model IDs and display names.
    """
    from agent.providers.dashscope import list_dashscope_models

    return list_dashscope_models()


@app.post("/api/subagents/run")
async def run_subagent_endpoint(request: SubagentRunRequest) -> dict:
    """
    Run a subagent directly (for testing/debugging).

    This endpoint bypasses the main agent and runs a subagent directly.
    Useful for testing subagent behavior.

    Args:
        subagent: Name of the subagent ("research" or "compiler")
        task: Task description for the subagent
        project_path: Optional project path (required for compiler)

    Returns:
        Result from the subagent
    """
    from agent.subagents import run_subagent, list_subagents

    # Validate subagent name
    available = list_subagents()
    available_names = [s["name"] for s in available]

    if request.subagent not in available_names:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown subagent: '{request.subagent}'. Available: {', '.join(available_names)}"
        )

    try:
        context = {}
        if request.project_path:
            context["project_path"] = request.project_path

        result = await run_subagent(
            name=request.subagent,
            task=request.task,
            context=context,
            project_path=request.project_path or "",
        )

        return result.to_dict()

    except Exception as e:
        logger.error(f"Subagent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Planning Endpoints ============

class CreatePlanRequest(BaseModel):
    task: str
    project_path: str
    project_name: Optional[str] = None
    session_id: Optional[str] = None


class UpdateStepRequest(BaseModel):
    step_id: str
    status: str  # "completed", "failed", "skipped"
    output: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    project_path: Optional[str] = None  # For persistence


class PlanSessionRequest(BaseModel):
    session_id: Optional[str] = None
    project_path: Optional[str] = None  # For persistence


@app.post("/api/planning/create")
async def create_plan_endpoint(request: CreatePlanRequest) -> dict:
    """
    Create a structured plan for a complex task.

    Uses the PlannerAgent to analyze the task and generate
    a step-by-step execution plan.

    Returns:
        The created plan with steps and metadata
    """
    from agent.subagents.planner import create_plan_for_task
    from agent.planning import get_plan_manager

    try:
        plan = await create_plan_for_task(
            task=request.task,
            project_path=request.project_path,
            project_name=request.project_name or "",
        )

        if not plan:
            raise HTTPException(
                status_code=500,
                detail="Failed to create plan. Please try with more details."
            )

        # Register the plan with the manager
        plan_manager = get_plan_manager()
        await plan_manager.create_plan(
            goal=plan.goal,
            original_request=request.task,
            steps=[s.to_dict() for s in plan.steps],
            session_id=request.session_id or "default",
            project_path=request.project_path,
            context=plan.context,
            complexity=plan.complexity,
            estimated_files=plan.estimated_files,
            risks=plan.risks,
            assumptions=plan.assumptions,
        )

        return {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "status": plan.status.value,
            "complexity": plan.complexity,
            "steps": [s.to_dict() for s in plan.steps],
            "estimated_files": plan.estimated_files,
            "risks": plan.risks,
            "assumptions": plan.assumptions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Planning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/planning/current")
async def get_current_plan_endpoint(session_id: Optional[str] = None) -> dict:
    """
    Get the current active plan for a session.

    Returns:
        The current plan with progress info, or empty if no plan
    """
    from agent.planning import get_plan_manager

    plan_manager = get_plan_manager()
    plan = await plan_manager.get_plan(session_id or "default")

    if not plan:
        return {
            "has_plan": False,
            "message": "No active plan",
        }

    return {
        "has_plan": True,
        "plan_id": plan.plan_id,
        "goal": plan.goal,
        "status": plan.status.value,
        "progress": plan.progress,
        "current_step": plan.current_step.to_dict() if plan.current_step else None,
        "steps": [s.to_dict() for s in plan.steps],
        "markdown": plan.to_markdown(),
    }


@app.post("/api/planning/start")
async def start_plan_endpoint(request: PlanSessionRequest) -> dict:
    """
    Start executing the current plan.

    Marks the plan as in-progress and returns the first step.
    """
    from agent.planning import get_plan_manager, PlanStatus

    plan_manager = get_plan_manager()
    session_id = request.session_id or "default"
    plan = await plan_manager.get_plan(session_id)

    if not plan:
        raise HTTPException(status_code=404, detail="No active plan")

    if plan.status not in [PlanStatus.DRAFT, PlanStatus.APPROVED]:
        raise HTTPException(
            status_code=400,
            detail=f"Plan is already {plan.status.value}"
        )

    # Approve and start
    await plan_manager.approve_plan(session_id)
    step = await plan_manager.start_next_step(session_id)

    return {
        "success": True,
        "status": "in_progress",
        "current_step": step.to_dict() if step else None,
    }


@app.post("/api/planning/step/complete")
async def complete_step_endpoint(request: UpdateStepRequest) -> dict:
    """
    Mark the current step as completed.

    Automatically advances to the next step if available.
    """
    from agent.planning import get_plan_manager, PlanStatus

    plan_manager = get_plan_manager()
    session_id = request.session_id or "default"

    plan = await plan_manager.get_plan(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No active plan")

    current = plan.current_step
    if not current:
        raise HTTPException(status_code=400, detail="No step in progress")

    # Complete current step
    await plan_manager.complete_current_step(
        output=request.output or "",
        session_id=session_id,
        project_path=request.project_path,
    )

    # Refresh plan
    plan = await plan_manager.get_plan(session_id)

    # Start next step if plan not complete
    next_step = None
    if plan.status != PlanStatus.COMPLETED:
        next_step = await plan_manager.start_next_step(session_id, project_path=request.project_path)

    return {
        "success": True,
        "completed_step": current.to_dict(),
        "plan_status": plan.status.value,
        "next_step": next_step.to_dict() if next_step else None,
        "progress": plan.progress,
    }


@app.post("/api/planning/step/fail")
async def fail_step_endpoint(request: UpdateStepRequest) -> dict:
    """
    Mark the current step as failed.
    """
    from agent.planning import get_plan_manager

    plan_manager = get_plan_manager()
    session_id = request.session_id or "default"

    plan = await plan_manager.get_plan(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No active plan")

    current = plan.current_step
    if not current:
        raise HTTPException(status_code=400, detail="No step in progress")

    # Fail current step
    await plan_manager.fail_current_step(
        error=request.error or "Step failed",
        session_id=session_id,
        project_path=request.project_path,
    )

    return {
        "success": True,
        "failed_step": current.to_dict(),
        "error": request.error,
    }


@app.post("/api/planning/step/skip")
async def skip_step_endpoint(request: UpdateStepRequest) -> dict:
    """
    Skip the current step.
    """
    from agent.planning import get_plan_manager, StepStatus

    plan_manager = get_plan_manager()
    session_id = request.session_id or "default"

    plan = await plan_manager.get_plan(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No active plan")

    current = plan.current_step
    if not current:
        raise HTTPException(status_code=400, detail="No step in progress")

    # Skip current step
    await plan_manager.update_step(
        current.step_id,
        StepStatus.SKIPPED,
        request.output or "Skipped",
        session_id=session_id,
        project_path=request.project_path,
    )

    # Start next step
    next_step = await plan_manager.start_next_step(session_id, project_path=request.project_path)

    return {
        "success": True,
        "skipped_step": current.to_dict(),
        "next_step": next_step.to_dict() if next_step else None,
    }


@app.post("/api/planning/cancel")
async def cancel_plan_endpoint(request: PlanSessionRequest) -> dict:
    """
    Cancel/abandon the current plan.
    """
    from agent.planning import get_plan_manager

    plan_manager = get_plan_manager()
    session_id = request.session_id or "default"

    plan = await plan_manager.get_plan(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No active plan")

    progress = plan.progress
    await plan_manager.cancel_plan(session_id, project_path=request.project_path)

    return {
        "success": True,
        "cancelled_goal": plan.goal,
        "progress_at_cancellation": progress,
    }


@app.get("/api/planning/history")
async def get_plan_history_endpoint(
    session_id: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """
    Get recent plan history for a session.

    Returns completed/cancelled plans for reference.
    """
    from agent.planning import get_plan_manager

    plan_manager = get_plan_manager()
    history = await plan_manager.get_history(session_id or "default", limit=limit)

    return {
        "count": len(history),
        "plans": [
            {
                "plan_id": p.plan_id,
                "goal": p.goal,
                "status": p.status.value,
                "progress": p.progress,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            }
            for p in history
        ],
    }


# ============ Memory Endpoints ============

@app.get("/api/memory")
async def get_memory(project_path: str):
    """Get all memory entries for a project."""
    service = MemoryService(project_path)
    memory = service.load()
    stats = service.get_stats()

    return {
        "entries": {
            "papers": memory.papers,
            "citations": memory.citations,
            "conventions": memory.conventions,
            "todos": memory.todos,
            "notes": memory.notes,
        },
        "stats": stats,
    }


@app.get("/api/memory/stats")
async def get_memory_stats(project_path: str):
    """Get memory token count and warning status."""
    service = MemoryService(project_path)
    return service.get_stats()


@app.post("/api/memory/papers")
async def add_paper(request: AddPaperRequest):
    """Add a paper entry."""
    service = MemoryService(request.project_path)
    entry = service.add_entry("papers", {
        "title": request.title,
        "authors": request.authors,
        "arxiv_id": request.arxiv_id,
        "summary": request.summary,
        "tags": request.tags,
    })
    return entry


@app.post("/api/memory/citations")
async def add_citation(request: AddCitationRequest):
    """Add a citation entry."""
    service = MemoryService(request.project_path)
    entry = service.add_entry("citations", {
        "bibtex_key": request.bibtex_key,
        "reason": request.reason,
        "paper_id": request.paper_id,
    })
    return entry


@app.post("/api/memory/conventions")
async def add_convention(request: AddConventionRequest):
    """Add a convention entry."""
    service = MemoryService(request.project_path)
    entry = service.add_entry("conventions", {
        "rule": request.rule,
        "example": request.example,
    })
    return entry


@app.post("/api/memory/todos")
async def add_todo(request: AddTodoRequest):
    """Add a todo entry."""
    service = MemoryService(request.project_path)
    entry = service.add_entry("todos", {
        "task": request.task,
        "priority": request.priority,
        "status": request.status,
    })
    return entry


@app.post("/api/memory/notes")
async def add_note(request: AddNoteRequest):
    """Add a note entry."""
    service = MemoryService(request.project_path)
    entry = service.add_entry("notes", {
        "content": request.content,
        "tags": request.tags,
    })
    return entry


@app.put("/api/memory/{entry_type}/{entry_id}")
async def update_memory_entry(
    entry_type: str,
    entry_id: str,
    request: UpdateEntryRequest,
):
    """Update a memory entry."""
    if entry_type not in ["papers", "citations", "conventions", "todos", "notes"]:
        raise HTTPException(status_code=400, detail=f"Invalid entry type: {entry_type}")

    service = MemoryService(request.project_path)
    entry = service.update_entry(entry_type, entry_id, request.data)

    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    return entry


@app.delete("/api/memory/{entry_type}/{entry_id}")
async def delete_memory_entry(
    entry_type: str,
    entry_id: str,
    project_path: str,
):
    """Delete a memory entry."""
    if entry_type not in ["papers", "citations", "conventions", "todos", "notes"]:
        raise HTTPException(status_code=400, detail=f"Invalid entry type: {entry_type}")

    service = MemoryService(project_path)
    success = service.delete_entry(entry_type, entry_id)

    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {"success": True}


class ClearMemoryRequest(BaseModel):
    project_path: str


@app.post("/api/memory/clear")
async def clear_memory(request: ClearMemoryRequest):
    """Clear all memory entries for a project."""
    from services.memory import MemoryData

    service = MemoryService(request.project_path)
    # Create a fresh empty memory
    empty_memory = MemoryData()
    service.save(empty_memory)

    return {"success": True, "message": "Memory cleared"}


# ============ Literature Verifier Endpoints ============

@app.post("/api/verify-references")
async def verify_references(request: VerifyReferencesRequest):
    """
    Verify all references in a project.
    Streams results as SSE events.
    """
    import httpx
    from openai import AsyncOpenAI
    from services.reference_verifier import ReferenceVerifier
    from services.memory import MemoryService

    async def generate():
        # Initialize clients
        http_client = httpx.AsyncClient()

        # Create OpenRouter client (OpenAI-compatible API)
        llm_client = AsyncOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
            http_client=http_client,
            default_headers={
                "HTTP-Referer": "https://github.com/ArcoCodes/OpenResearch",
                "X-Title": "OpenResearch LaTeX IDE",
            },
        )
        model_name = "anthropic/claude-3.5-haiku"

        try:
            verifier = ReferenceVerifier(
                project_path=request.project_path,
                http_client=http_client,
                llm_client=llm_client,
                bib_file=request.bib_file,
                model_name=model_name,
            )

            # Get approved citations
            memory = MemoryService(request.project_path)
            approved = set(memory.get_approved_citations())

            # Send started event
            yield {
                "event": "started",
                "data": json.dumps({"project_path": request.project_path}),
            }

            stats = {"verified": 0, "warnings": 0, "errors": 0}

            async for result in verifier.verify_all():
                # Skip if already approved
                if result.cite_key in approved:
                    result.status = "verified"
                    result.context_explanation = "Manually approved"

                # Update stats
                if result.status == "verified":
                    stats["verified"] += 1
                elif result.status == "warning":
                    stats["warnings"] += 1
                else:
                    stats["errors"] += 1

                yield {
                    "event": "result",
                    "data": json.dumps(result.to_dict()),
                }

            yield {
                "event": "complete",
                "data": json.dumps(stats),
            }

        finally:
            await http_client.aclose()

    return EventSourceResponse(generate())


@app.get("/api/verify-references/state")
async def get_verifier_state(project_path: str):
    """Get saved verifier state (approved citations)."""
    from services.memory import MemoryService

    memory = MemoryService(project_path)
    return {
        "approved_citations": memory.get_approved_citations(),
    }


@app.get("/api/verify-references/pairs")
async def get_tex_bib_pairs(project_path: str):
    """
    Find all .tex and .bib file pairs in the project.
    Returns pairs with matching filenames (e.g., main.tex + main.bib).
    """
    from pathlib import Path

    project = Path(project_path)
    if not project.exists():
        return {"pairs": [], "error": "Project path does not exist"}

    # Find all .tex and .bib files recursively
    tex_files = list(project.glob("**/*.tex"))
    bib_files = list(project.glob("**/*.bib"))

    # Create a map of bib files by their stem (filename without extension)
    bib_map = {}
    for bib in bib_files:
        stem = bib.stem
        if stem not in bib_map:
            bib_map[stem] = []
        bib_map[stem].append(bib)

    # Find pairs with matching names
    pairs = []
    seen_bibs = set()

    for tex in tex_files:
        stem = tex.stem
        if stem in bib_map:
            for bib in bib_map[stem]:
                if str(bib) not in seen_bibs:
                    pairs.append({
                        "tex_file": str(tex.relative_to(project)),
                        "bib_file": str(bib.relative_to(project)),
                        "display_name": f"{stem} ({bib.relative_to(project).parent or '.'})",
                    })
                    seen_bibs.add(str(bib))

    # Also add any bib files without matching tex files
    for bib in bib_files:
        if str(bib) not in seen_bibs:
            pairs.append({
                "tex_file": None,
                "bib_file": str(bib.relative_to(project)),
                "display_name": f"{bib.stem} ({bib.relative_to(project).parent or '.'})",
            })

    return {"pairs": pairs, "total_tex": len(tex_files), "total_bib": len(bib_files)}


@app.post("/api/verify-references/approve")
async def approve_reference(request: ApproveReferenceRequest):
    """Approve a reference manually."""
    from services.memory import MemoryService

    memory = MemoryService(request.project_path)
    memory.approve_citation(request.cite_key)
    return {"success": True, "cite_key": request.cite_key}


@app.post("/api/verify-references/unapprove")
async def unapprove_reference(request: ApproveReferenceRequest):
    """Remove approval from a reference."""
    from services.memory import MemoryService

    memory = MemoryService(request.project_path)
    memory.unapprove_citation(request.cite_key)
    return {"success": True, "cite_key": request.cite_key}


# ============ Git/Overleaf Sync Endpoints ============

class SyncSetupRequest(BaseModel):
    project_path: str
    overleaf_url: str
    username: Optional[str] = None
    password: Optional[str] = None


class SyncRequest(BaseModel):
    project_path: str
    commit_message: Optional[str] = None
    filepath: Optional[str] = None  # Only sync this file if specified


class SyncStatusRequest(BaseModel):
    project_path: str


@app.post("/api/sync/status")
async def get_sync_status(request: SyncStatusRequest) -> dict:
    """
    Get synchronization status for a project.

    Returns information about git state, remote connection,
    and pending changes.
    """
    from services.git_sync import GitSyncService

    sync = GitSyncService(request.project_path)
    status = await sync.get_status()

    return status.to_dict()


@app.post("/api/sync/setup")
async def setup_sync(request: SyncSetupRequest) -> dict:
    """
    Set up Git/Overleaf synchronization for a project.

    Args:
        project_path: Path to the LaTeX project
        overleaf_url: Overleaf git URL (https://git.overleaf.com/<project_id>)
        username: Overleaf email (optional)
        password: Overleaf password or token (optional)

    The Overleaf git URL can be found in:
    Project Settings > Git Integration > Clone URL
    """
    from services.git_sync import GitSyncService

    sync = GitSyncService(request.project_path)
    result = await sync.setup(
        overleaf_url=request.overleaf_url,
        username=request.username,
        password=request.password,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return result.to_dict()


@app.post("/api/sync/pull")
async def sync_pull(request: SyncRequest) -> dict:
    """
    Pull changes from Overleaf.

    Downloads new changes from the Overleaf server and merges
    them with local files. Local uncommitted changes are stashed
    and reapplied after the pull.
    """
    from services.git_sync import GitSyncService

    sync = GitSyncService(request.project_path)
    result = await sync.pull()

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return result.to_dict()


@app.post("/api/sync/push")
async def sync_push(request: SyncRequest) -> dict:
    """
    Push local changes to Overleaf.

    Commits any uncommitted changes and pushes them to Overleaf.
    If the remote has new changes, you'll need to pull first.
    """
    from services.git_sync import GitSyncService

    sync = GitSyncService(request.project_path)
    result = await sync.push(commit_message=request.commit_message)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return result.to_dict()


@app.post("/api/sync")
async def sync_project(request: SyncRequest) -> dict:
    """
    Full sync: pull then push.

    This is the recommended sync operation as it handles
    both incoming and outgoing changes in one operation.

    If filepath is specified, only that file will be committed and pushed.
    """
    from services.git_sync import GitSyncService

    sync = GitSyncService(request.project_path)
    result = await sync.sync(commit_message=request.commit_message, filepath=request.filepath)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return result.to_dict()


class ResolveConflictRequest(BaseModel):
    project_path: str
    filepath: str
    keep: str = "ours"  # "ours" or "theirs"


@app.post("/api/sync/resolve")
async def resolve_conflict(request: ResolveConflictRequest) -> dict:
    """
    Resolve a merge conflict by choosing a version.

    Args:
        filepath: Path to the conflicted file
        keep: "ours" (local version) or "theirs" (remote version)
    """
    from services.git_sync import GitSyncService

    if request.keep not in ("ours", "theirs"):
        raise HTTPException(
            status_code=400,
            detail="keep must be 'ours' or 'theirs'"
        )

    sync = GitSyncService(request.project_path)
    result = await sync.resolve_conflict(request.filepath, keep=request.keep)

    return result.to_dict()


@app.post("/api/sync/abort")
async def abort_merge(request: SyncRequest) -> dict:
    """
    Abort an in-progress merge.

    Use this to cancel a merge that has conflicts and start fresh.
    """
    from services.git_sync import GitSyncService

    sync = GitSyncService(request.project_path)
    result = await sync.abort_merge()

    return result.to_dict()


# ============ Vibe Research Endpoints ============

@app.post("/api/vibe-research/start")
async def start_vibe_research(request: VibeResearchStartRequest) -> dict:
    """
    Start a new vibe research session.

    Vibe research is AI-led autonomous research that:
    1. Clarifies scope with the user
    2. Discovers relevant papers via arXiv and Semantic Scholar
    3. Synthesizes themes from the literature
    4. Identifies research gaps
    5. Generates novel hypotheses
    6. Evaluates and ranks hypotheses

    Args:
        project_path: Path to the LaTeX project
        topic: Research topic or question
        max_papers: Maximum papers to discover (default: 100)
        max_papers_to_read: Maximum papers to read in full (default: 30)
        target_hypotheses: Target number of hypotheses (default: 5)

    Returns:
        Session info including session_id
    """
    from agent.vibe_state import VibeResearchState

    # Create new state
    state = VibeResearchState(
        topic=request.topic,
        max_papers=request.max_papers,
        max_papers_to_read=request.max_papers_to_read,
        target_hypotheses=request.target_hypotheses,
    )

    # Save to project
    state.save(request.project_path)

    return {
        "session_id": state.session_id,
        "topic": state.topic,
        "phase": state.current_phase.value,
        "created_at": state.created_at,
        "config": {
            "max_papers": state.max_papers,
            "max_papers_to_read": state.max_papers_to_read,
            "target_hypotheses": state.target_hypotheses,
        },
    }


@app.get("/api/vibe-research/sessions")
async def list_vibe_sessions(project_path: str) -> dict:
    """
    List all vibe research sessions for a project.

    Returns sessions sorted by creation date (newest first).
    """
    from agent.vibe_state import VibeResearchState

    sessions = VibeResearchState.list_sessions(project_path)

    return {
        "count": len(sessions),
        "sessions": sessions,
    }


@app.get("/api/vibe-research/status/{session_id}")
async def get_vibe_status(session_id: str, project_path: str) -> dict:
    """
    Get status summary for a vibe research session.

    Returns phase, progress, and counts.
    """
    from agent.vibe_state import VibeResearchState

    state = VibeResearchState.load(project_path, session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {
        "session_id": state.session_id,
        "topic": state.topic,
        "phase": state.current_phase.value,
        "progress": state.phase_progress.get(state.current_phase.value, 0),
        "is_complete": state.is_complete,
        "stall_count": state.stall_count,
        "papers_found": len(state.papers),
        "papers_read": len(state.papers_read),
        "themes_count": len(state.themes),
        "gaps_count": len(state.gaps),
        "hypotheses_count": len(state.hypotheses),
    }


@app.get("/api/vibe-research/state/{session_id}")
async def get_vibe_state(session_id: str, project_path: str) -> dict:
    """
    Get full state for a vibe research session.

    Returns complete state including papers, themes, gaps, and hypotheses.
    """
    from agent.vibe_state import VibeResearchState

    state = VibeResearchState.load(project_path, session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return state.to_dict()


@app.get("/api/vibe-research/report/{session_id}")
async def get_vibe_report(session_id: str, project_path: str) -> dict:
    """
    Get the final report for a completed vibe research session.

    Returns the generated report and ranked hypotheses.
    """
    from agent.vibe_state import VibeResearchState
    from pathlib import Path

    state = VibeResearchState.load(project_path, session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    if not state.is_complete:
        return {
            "session_id": state.session_id,
            "is_complete": False,
            "phase": state.current_phase.value,
            "message": "Research is still in progress",
            "report": "",
            "report_path": None,
            "hypotheses": [],
        }

    # Check if report files exist in subdirectory
    base_filename = state.get_report_filename()
    report_dir = Path(project_path) / "report" / base_filename
    tex_filename = f"{base_filename}.tex"
    bib_filename = f"{base_filename}.bib"
    tex_path = report_dir / tex_filename
    bib_path = report_dir / bib_filename

    return {
        "session_id": state.session_id,
        "is_complete": True,
        "topic": state.topic,
        "report": state.report,
        "report_path": str(tex_path) if tex_path.exists() else None,
        "report_filename": f"report/{base_filename}/{tex_filename}",
        "bib_path": str(bib_path) if bib_path.exists() else None,
        "bib_filename": f"report/{base_filename}/{bib_filename}",
        "hypotheses": state.get_ranked_hypotheses(),
        "papers_count": len(state.papers),
        "themes_count": len(state.themes),
        "gaps_count": len(state.gaps),
    }


@app.post("/api/vibe-research/run/{session_id}")
async def run_vibe_iteration(session_id: str, request: VibeResearchRunRequest) -> dict:
    """
    Run one iteration of vibe research.

    The research agent will perform one action based on current state.
    Call this repeatedly until is_complete=True or use streaming endpoint.

    Returns:
        Updated status and the action taken
    """
    from agent.vibe_state import VibeResearchState, ResearchPhase
    from agent.subagents.research import ResearchAgent, ResearchMode

    state = VibeResearchState.load(request.project_path, session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    if state.is_complete:
        return {
            "session_id": state.session_id,
            "is_complete": True,
            "message": "Research already complete",
            "phase": state.current_phase.value,
        }

    # Run one iteration via research agent in VIBE mode
    try:
        # Mark session as running
        _running_vibe_sessions[session_id] = True

        # Extract provider config
        provider_config = None
        if request.provider:
            provider_config = {
                "name": request.provider.name,
                "model": request.provider.model,
                "api_key": request.provider.api_key,
            }

        # Create agent in VIBE mode (uses longer timeout)
        agent = ResearchAgent(mode=ResearchMode.VIBE, provider_config=provider_config)

        # Determine task based on phase
        phase_tasks = {
            ResearchPhase.SCOPING: f"Clarify the scope for research on: {state.topic}",
            ResearchPhase.DISCOVERY: f"Search for papers on: {state.topic}",
            ResearchPhase.SYNTHESIS: "Analyze papers and identify themes",
            ResearchPhase.IDEATION: "Identify gaps and generate hypotheses",
            ResearchPhase.EVALUATION: "Score and rank hypotheses",
        }
        task = phase_tasks.get(state.current_phase, f"Continue research on: {state.topic}")

        result = await agent.run(
            task=task,
            project_path=request.project_path,
            mode=ResearchMode.VIBE,
            vibe_state=state,
        )

        # Check if stopped
        if not _running_vibe_sessions.get(session_id, True):
            return {
                "session_id": session_id,
                "is_complete": False,
                "stopped": True,
                "message": "Research stopped by user",
                "phase": state.current_phase.value,
            }

        # Reload state (agent may have modified it)
        state = VibeResearchState.load(request.project_path, session_id)

        return {
            "session_id": state.session_id,
            "is_complete": state.is_complete,
            "phase": state.current_phase.value,
            "progress": state.phase_progress.get(state.current_phase.value, 0),
            "last_action": state.last_action,
            "output": result.output if result else "",
            "papers_found": len(state.papers),
            "hypotheses_count": len(state.hypotheses),
        }

    except Exception as e:
        logger.error(f"Vibe research error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up running state
        _running_vibe_sessions.pop(session_id, None)


@app.post("/api/vibe-research/stream/{session_id}")
async def stream_vibe_research(session_id: str, request: VibeResearchRunRequest):
    """
    Stream vibe research progress via Server-Sent Events.

    Runs the research agent continuously until completion or error,
    streaming progress updates.
    """
    from agent.vibe_state import VibeResearchState, ResearchPhase
    from agent.subagents.research import ResearchAgent, ResearchMode

    state = VibeResearchState.load(request.project_path, session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    async def event_generator():
        nonlocal state

        try:
            # Extract provider config
            provider_config = None
            if request.provider:
                provider_config = {
                    "name": request.provider.name,
                    "model": request.provider.model,
                    "api_key": request.provider.api_key,
                }

            # Create agent in VIBE mode (uses longer timeout)
            agent = ResearchAgent(mode=ResearchMode.VIBE, provider_config=provider_config)

            while not state.is_complete:
                # Yield current status
                yield {
                    "event": "status",
                    "data": json.dumps({
                        "type": "status",
                        "phase": state.current_phase.value,
                        "progress": state.phase_progress.get(state.current_phase.value, 0),
                        "papers_found": len(state.papers),
                        "hypotheses_count": len(state.hypotheses),
                    }),
                }

                # Determine task
                phase_tasks = {
                    ResearchPhase.SCOPING: f"Clarify the scope for research on: {state.topic}",
                    ResearchPhase.DISCOVERY: f"Search for papers on: {state.topic}",
                    ResearchPhase.SYNTHESIS: "Analyze papers and identify themes",
                    ResearchPhase.IDEATION: "Identify gaps and generate hypotheses",
                    ResearchPhase.EVALUATION: "Score and rank hypotheses",
                }
                task = phase_tasks.get(state.current_phase, f"Continue research on: {state.topic}")

                # Run iteration
                result = await agent.run(
                    task=task,
                    project_path=request.project_path,
                    mode=ResearchMode.VIBE,
                    vibe_state=state,
                )

                # Reload state
                state = VibeResearchState.load(request.project_path, session_id)

                # Yield action
                yield {
                    "event": "action",
                    "data": json.dumps({
                        "type": "action",
                        "action": state.last_action,
                        "output": result.output[:500] if result else "",
                    }),
                }

            # Complete
            yield {
                "event": "complete",
                "data": json.dumps({
                    "type": "complete",
                    "session_id": state.session_id,
                    "hypotheses_count": len(state.hypotheses),
                }),
            }

        except Exception as e:
            logger.error(f"Vibe research stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({
                    "type": "error",
                    "message": str(e),
                }),
            }

    return EventSourceResponse(event_generator())


# Track running vibe research sessions for cancellation
_running_vibe_sessions: dict[str, bool] = {}


@app.delete("/api/vibe-research/{session_id}")
async def delete_vibe_session(session_id: str, project_path: str) -> dict:
    """
    Delete a vibe research session.

    Args:
        session_id: The session ID to delete
        project_path: Path to the project

    Returns:
        Confirmation of deletion
    """
    from pathlib import Path

    # Check if session exists
    aura_dir = Path(project_path) / ".aura"
    state_file = aura_dir / f"vibe_research_{session_id}.json"

    if not state_file.exists():
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    # Mark as stopped if running
    _running_vibe_sessions[session_id] = False

    # Delete the file
    state_file.unlink()

    return {
        "success": True,
        "message": f"Session {session_id} deleted",
    }


@app.post("/api/vibe-research/stop/{session_id}")
async def stop_vibe_session(session_id: str) -> dict:
    """
    Stop a running vibe research session.

    This sets a flag that will be checked by the running agent.
    The agent will stop after completing its current action.

    Args:
        session_id: The session ID to stop

    Returns:
        Confirmation that stop was requested
    """
    _running_vibe_sessions[session_id] = False

    return {
        "success": True,
        "message": f"Stop requested for session {session_id}",
    }


def is_session_running(session_id: str) -> bool:
    """Check if a session should continue running."""
    return _running_vibe_sessions.get(session_id, True)


def mark_session_running(session_id: str):
    """Mark a session as running."""
    _running_vibe_sessions[session_id] = True


def mark_session_stopped(session_id: str):
    """Mark a session as stopped."""
    _running_vibe_sessions.pop(session_id, None)


# ============ Writing Intelligence Endpoints ============

class AnalyzeStructureRequest(BaseModel):
    project_path: str
    filepath: str = "main.tex"


class OutlineRequest(BaseModel):
    project_path: str
    filepath: str = "main.tex"


@app.post("/api/outline")
async def api_get_outline(request: OutlineRequest):
    """Get document outline as nested tree structure for File Outline panel."""
    from pathlib import Path
    from services.latex_parser import parse_sections, build_section_tree

    filepath = Path(request.project_path) / request.filepath

    # SECURITY: Path traversal check
    try:
        filepath.resolve().relative_to(Path(request.project_path).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filepath")

    if not filepath.exists():
        return {"outline": [], "success": True}

    content = filepath.read_text(encoding="utf-8", errors="replace")
    sections = parse_sections(content)
    tree = build_section_tree(sections)

    def section_to_dict(section) -> dict:
        """Convert DocumentSection to dict with children."""
        return {
            "name": section.name,
            "level": section.level,
            "line": section.line_start,
            "label": section.label,
            "children": [section_to_dict(child) for child in section.children],
        }

    return {
        "outline": [section_to_dict(s) for s in tree],
        "success": True,
    }


class CreateTableRequest(BaseModel):
    project_path: str
    data: str
    caption: str
    label: str = ""
    style: str = "booktabs"


class CreateFigureRequest(BaseModel):
    project_path: str
    description: str
    figure_type: str = "tikz"
    caption: str = ""
    label: str = ""
    data: str = ""


@app.post("/api/analyze-structure")
async def api_analyze_structure(request: AnalyzeStructureRequest):
    """Analyze document structure."""
    from pathlib import Path

    filepath = Path(request.project_path) / request.filepath

    # SECURITY: Path traversal check
    try:
        filepath.resolve().relative_to(Path(request.project_path).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filepath")

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = filepath.read_text()
    structure = parse_document(content)

    return {
        "sections": [
            {
                "name": s.name,
                "level": s.level,
                "line_start": s.line_start,
                "line_end": s.line_end,
                "label": s.label,
            }
            for s in structure.sections
        ],
        "elements": [
            {
                "type": e.type,
                "caption": e.caption,
                "label": e.label,
                "line_start": e.line_start,
                "line_end": e.line_end,
            }
            for e in structure.elements
        ],
        "citations": [
            {
                "key": c.key,
                "locations": c.locations,
                "command": c.command,
            }
            for c in structure.citations
        ],
        "citation_style": structure.citation_style,
        "bib_file": structure.bib_file,
        "packages": structure.packages,
    }


@app.post("/api/clean-bibliography")
async def api_clean_bibliography(request: AnalyzeStructureRequest):
    """Find unused bibliography entries."""
    from pathlib import Path

    filepath = Path(request.project_path) / request.filepath

    # SECURITY: Path traversal check
    try:
        filepath.resolve().relative_to(Path(request.project_path).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filepath")

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = filepath.read_text()
    structure = parse_document(content)

    if not structure.bib_file:
        return {"unused": [], "message": "No bibliography file detected"}

    bib_path = Path(request.project_path) / structure.bib_file

    # SECURITY: Path traversal check for bib file
    try:
        bib_path.resolve().relative_to(Path(request.project_path).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid bibliography path")

    if not bib_path.exists():
        raise HTTPException(status_code=404, detail=f"Bibliography file not found: {structure.bib_file}")

    bib_entries = parse_bib_file_path(bib_path)
    unused = find_unused_citations(structure.citations, bib_entries)

    return {
        "unused": [
            {
                "key": e.key,
                "title": e.fields.get("title", ""),
                "year": e.fields.get("year", ""),
            }
            for e in unused
        ],
        "total_entries": len(bib_entries),
        "cited_count": len(structure.citations),
    }


# ============ Run Server ============

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Aura Backend Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
