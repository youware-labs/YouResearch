"""
Docker LaTeX compilation service.

Runs pdflatex in an isolated Docker container for safe, reproducible compilation.
"""

import asyncio
import docker
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Use pre-built image from Docker Hub (much faster than building)
# Options:
# - "texlive/texlive:latest" - Full TexLive (~5GB, most complete)
# - "texlive/texlive:latest-small" - Smaller TexLive (~1GB)
# - "blang/latex:latest" - Lightweight alternative (~800MB)
# Prefer full image for better package support, fall back to smaller ones
IMAGE_NAME = "texlive/texlive:latest"
FALLBACK_IMAGES = ["texlive/texlive:latest-small", "blang/latex:latest"]
DOCKERFILE_PATH = Path(__file__).parent.parent.parent / "sandbox"

# Friendly error message for Docker not being installed
DOCKER_NOT_INSTALLED_MESSAGE = """Docker is not installed or not running.

OpenResearch uses Docker to compile LaTeX documents in a safe, isolated environment.

📥 **How to Install Docker Desktop:**

1. Download Docker Desktop for Mac from:
   https://www.docker.com/products/docker-desktop/

2. Open the downloaded .dmg file and drag Docker to Applications

3. Launch Docker from Applications

4. Wait for Docker to start (you'll see a whale icon in the menu bar)

5. Return to OpenResearch and try compiling again!

💡 **Tip:** Docker Desktop is free for personal use and educational purposes.

🔗 **Direct Download Link:**
https://desktop.docker.com/mac/main/arm64/Docker.dmg
"""

DOCKER_NOT_RUNNING_MESSAGE = """Docker is installed but not running.

Please start Docker Desktop:

1. Open Docker from your Applications folder
2. Wait for the whale icon to appear in the menu bar
3. Once Docker shows "Docker Desktop is running", try compiling again!

💡 **Tip:** You can set Docker to start automatically on login in Docker Desktop preferences.
"""


class DockerNotAvailableError(Exception):
    """Raised when Docker is not available."""
    def __init__(self, message: str, is_installed: bool = False):
        super().__init__(message)
        self.message = message
        self.is_installed = is_installed


@dataclass
class CompileResult:
    """Result of a LaTeX compilation."""
    success: bool
    pdf_path: Optional[str] = None
    log_output: str = ""
    error_summary: str = ""
    docker_not_available: bool = False  # Flag to indicate Docker issue


class DockerLatex:
    """
    LaTeX compilation service using Docker.

    Compiles .tex files in an isolated texlive container.
    """

    def __init__(self):
        self.client = None
        self.docker_available = False
        self.docker_installed = False
        self._init_docker()

    def _init_docker(self) -> None:
        """Initialize Docker client and check availability."""
        self._check_docker_status()

    def _check_docker_status(self) -> None:
        """Check Docker availability (can be called to refresh status)."""
        try:
            self.client = docker.from_env()
            self.client.ping()
            self.docker_installed = True
            self.docker_available = True
            self._ensure_image()
        except docker.errors.DockerException as e:
            # Docker is installed but not running
            if "connection refused" in str(e).lower() or "connect" in str(e).lower():
                self.docker_installed = True
                self.docker_available = False
                logger.warning("Docker is installed but not running")
            else:
                # Docker might not be installed
                self.docker_installed = False
                self.docker_available = False
                logger.warning(f"Docker not available: {e}")
        except Exception as e:
            self.docker_installed = False
            self.docker_available = False
            logger.warning(f"Docker not available: {e}")

    def _ensure_image(self) -> None:
        """Pull the texlive image if it doesn't exist."""
        try:
            self.client.images.get(IMAGE_NAME)
            logger.info(f"Docker image '{IMAGE_NAME}' found")
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling Docker image '{IMAGE_NAME}' (this may take a few minutes on first run)...")
            try:
                self.client.images.pull(IMAGE_NAME)
                logger.info(f"Docker image '{IMAGE_NAME}' pulled successfully")
            except Exception as e:
                logger.warning(f"Failed to pull {IMAGE_NAME}: {e}, trying fallback...")
                for fallback in FALLBACK_IMAGES:
                    try:
                        self.client.images.pull(fallback)
                        logger.info(f"Fallback image '{fallback}' pulled successfully")
                        break
                    except Exception as e2:
                        logger.warning(f"Failed to pull {fallback}: {e2}")
                        continue

    def _get_available_image(self) -> str:
        """Get the name of an available texlive image."""
        for image_name in [IMAGE_NAME] + FALLBACK_IMAGES:
            try:
                self.client.images.get(image_name)
                return image_name
            except docker.errors.ImageNotFound:
                continue
        # If none found, return primary (will be pulled on first use)
        return IMAGE_NAME

    async def compile(
        self,
        project_path: str,
        filename: str = "main.tex",
        timeout: int = 120,
        runs: int = 2,
    ) -> CompileResult:
        """
        Compile a LaTeX file to PDF.

        Args:
            project_path: Path to the project directory
            filename: Name of the .tex file to compile
            timeout: Maximum time in seconds for compilation
            runs: Number of pdflatex runs (2 for references, 3 for complex docs)

        Returns:
            CompileResult with success status, paths, and logs
        """
        # Check if Docker is available
        if not self.docker_available:
            if self.docker_installed:
                return CompileResult(
                    success=False,
                    error_summary=DOCKER_NOT_RUNNING_MESSAGE,
                    docker_not_available=True
                )
            else:
                return CompileResult(
                    success=False,
                    error_summary=DOCKER_NOT_INSTALLED_MESSAGE,
                    docker_not_available=True
                )

        project_path = Path(project_path).resolve()

        if not project_path.exists():
            return CompileResult(
                success=False,
                error_summary=f"Project path does not exist: {project_path}"
            )

        tex_file = project_path / filename
        if not tex_file.exists():
            return CompileResult(
                success=False,
                error_summary=f"TeX file not found: {filename}"
            )

        # Build compilation command (run multiple times for references)
        # Use ; instead of && because pdflatex returns non-zero on warnings
        # but still generates the PDF
        base_name = Path(filename).stem  # Just the filename without extension or path
        tex_dir = str(Path(filename).parent) if "/" in filename else "."

        commands = []
        for i in range(runs):
            # Use -output-directory to put PDF in same dir as source
            # -synctex=1 generates .synctex.gz for PDF-to-source navigation
            if tex_dir != ".":
                commands.append(f"pdflatex -synctex=1 -interaction=nonstopmode -output-directory={tex_dir} {filename}")
            else:
                commands.append(f"pdflatex -synctex=1 -interaction=nonstopmode {filename}")

        # Check for bibliography
        bib_files = list(project_path.glob("**/*.bib"))
        if bib_files:
            # Insert biber/bibtex after first pdflatex (run from the tex directory)
            if tex_dir != ".":
                commands.insert(1, f"cd {tex_dir} && (biber {base_name} || bibtex {base_name} || true)")
            else:
                commands.insert(1, f"biber {base_name} || bibtex {base_name} || true")

        # Use ; to continue even if pdflatex has warnings
        full_command = " ; ".join(commands)

        def _run_container():
            try:
                # Get the available image
                image_to_use = self._get_available_image()

                # Capture both stdout and stderr, and don't fail on non-zero exit
                # LaTeX often exits with code 1 even when PDF is generated (due to warnings)
                output = self.client.containers.run(
                    image_to_use,
                    command=f"/bin/bash -c '{full_command} 2>&1; echo \"\\nEXIT_CODE=$?\"'",
                    volumes={str(project_path): {"bind": "/workspace", "mode": "rw"}},
                    working_dir="/workspace",
                    remove=True,
                    detach=False,
                    stdout=True,
                    stderr=True,
                    mem_limit="1g",
                    network_mode="none",  # No network access for security
                )
                return output.decode("utf-8")
            except docker.errors.ContainerError as e:
                # Even on ContainerError, the output might have useful info
                # and the PDF might have been generated
                error_output = ""
                if e.stderr:
                    error_output = e.stderr.decode("utf-8") if isinstance(e.stderr, bytes) else str(e.stderr)
                if not error_output:
                    # Try to get any output from the exception
                    error_output = str(e)
                logger.warning(f"Container exited with error but may have produced output: {e.exit_status}")
                return error_output
            except docker.errors.APIError as e:
                logger.error(f"Docker API error: {e}")
                return f"Docker API error: {e}"
            except Exception as e:
                logger.error(f"Unexpected error during compilation: {e}")
                return str(e)

        try:
            loop = asyncio.get_event_loop()
            log_output = await asyncio.wait_for(
                loop.run_in_executor(None, _run_container),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return CompileResult(
                success=False,
                log_output="",
                error_summary=f"Compilation timed out after {timeout} seconds"
            )

        # Check if PDF was generated (in same directory as the tex file)
        if tex_dir != ".":
            pdf_path = project_path / tex_dir / f"{base_name}.pdf"
        else:
            pdf_path = project_path / f"{base_name}.pdf"

        if pdf_path.exists():
            # PDF generated - check for warnings in the log
            warnings = self._extract_warnings(log_output)
            return CompileResult(
                success=True,
                pdf_path=str(pdf_path),
                log_output=log_output,
                error_summary=warnings  # Include warnings even on success
            )
        else:
            return CompileResult(
                success=False,
                pdf_path=None,
                log_output=log_output,
                error_summary=self._extract_errors(log_output)
            )

    def _extract_errors(self, log: str) -> str:
        """Extract error messages from LaTeX log output."""
        errors = []
        lines = log.split("\n")

        for i, line in enumerate(lines):
            # LaTeX errors start with !
            if line.startswith("!"):
                # Get the error and next few lines for context
                error_lines = [line]
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j].startswith("!") or lines[j].startswith("l."):
                        error_lines.append(lines[j])
                        if lines[j].startswith("l."):
                            break
                errors.append("\n".join(error_lines))

            # Also catch "Error:" messages
            elif "Error:" in line or "Fatal error" in line:
                errors.append(line)

        if errors:
            return "\n\n".join(errors[:5])  # Limit to first 5 errors

        # If no specific errors found, return last 500 chars of log
        return f"Compilation failed. Log tail:\n{log[-500:]}"

    def _extract_warnings(self, log: str) -> str:
        """Extract warning messages from LaTeX log output (when PDF was generated)."""
        warnings = []
        lines = log.split("\n")

        for line in lines:
            # LaTeX warnings
            if "LaTeX Warning:" in line:
                warnings.append(line.strip())
            # Package warnings
            elif "Package" in line and "Warning" in line:
                warnings.append(line.strip())
            # Undefined references/citations
            elif "undefined" in line.lower() and ("reference" in line.lower() or "citation" in line.lower()):
                warnings.append(line.strip())

        if warnings:
            # Deduplicate and limit
            unique_warnings = list(dict.fromkeys(warnings))[:5]
            return "\n".join(unique_warnings)

        return ""

    async def check_syntax(self, project_path: str, filename: str = "main.tex") -> CompileResult:
        """
        Quick syntax check without full compilation.

        Uses -draftmode for faster checking.
        """
        # Check if Docker is available
        if not self.docker_available:
            if self.docker_installed:
                return CompileResult(
                    success=False,
                    error_summary=DOCKER_NOT_RUNNING_MESSAGE,
                    docker_not_available=True
                )
            else:
                return CompileResult(
                    success=False,
                    error_summary=DOCKER_NOT_INSTALLED_MESSAGE,
                    docker_not_available=True
                )

        project_path = Path(project_path).resolve()
        tex_file = project_path / filename

        if not tex_file.exists():
            return CompileResult(
                success=False,
                error_summary=f"TeX file not found: {filename}"
            )

        def _run_check():
            try:
                output = self.client.containers.run(
                    IMAGE_NAME,
                    command=f"pdflatex -interaction=nonstopmode -draftmode -halt-on-error {filename}",
                    volumes={str(project_path): {"bind": "/workspace", "mode": "rw"}},
                    working_dir="/workspace",
                    remove=True,
                    detach=False,
                    stdout=True,
                    stderr=True,
                    mem_limit="512m",
                    network_mode="none",
                )
                return True, output.decode("utf-8")
            except docker.errors.ContainerError as e:
                return False, e.stderr.decode("utf-8") if e.stderr else str(e)

        loop = asyncio.get_event_loop()
        success, log_output = await loop.run_in_executor(None, _run_check)

        if success:
            return CompileResult(success=True, log_output=log_output)
        else:
            return CompileResult(
                success=False,
                log_output=log_output,
                error_summary=self._extract_errors(log_output)
            )

    def is_available(self) -> bool:
        """Check if Docker is available and the image exists."""
        try:
            # Re-check Docker status in case it was started after backend init
            if not self.docker_available:
                self._check_docker_status()

            if not self.client:
                return False

            self.client.ping()
            self.client.images.get(IMAGE_NAME)
            self.docker_available = True
            return True
        except Exception:
            return False


# Singleton instance
_docker_latex: DockerLatex | None = None


def get_docker_latex() -> DockerLatex:
    """Get or create the singleton DockerLatex instance."""
    global _docker_latex
    if _docker_latex is None:
        _docker_latex = DockerLatex()
    return _docker_latex
