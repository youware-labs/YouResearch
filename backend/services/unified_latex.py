"""
Unified LaTeX compilation service.

Provides a single interface for LaTeX compilation, automatically selecting
between available backends.

Priority:
1. Local TeX (if available) - fastest, best compatibility with images/packages
2. Docker (if running) - full TeX Live, handles complex documents with images
3. Tectonic (bundled) - works out of box, good for simple documents only
4. Error message with installation instructions

Note: Tectonic has limitations with image paths and some packages,
so we prefer Local TeX or Docker when available.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Literal

from services.tectonic_latex import get_tectonic_latex, TectonicLatex, TectonicCompileResult
from services.local_latex import get_local_latex, LocalLatex, LocalCompileResult
from services.docker import get_docker_latex, DockerLatex, CompileResult as DockerCompileResult

logger = logging.getLogger(__name__)


CompilationBackend = Literal["auto", "tectonic", "local", "docker"]


@dataclass
class CompileResult:
    """Unified compilation result."""
    success: bool
    pdf_path: Optional[str] = None
    log: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_summary: Optional[str] = None
    backend_used: Optional[str] = None  # "tectonic", "local", or "docker"
    tex_not_available: bool = False  # Flag for no TeX available


# Installation instructions
NO_TEX_AVAILABLE_MESSAGE = """No LaTeX compiler available.

This is unexpected - Tectonic should be bundled with the application.
Please try restarting the application.

If the issue persists, you have two options:

## Option 1: Install MacTeX (Recommended for Mac users)
1. Download MacTeX from: https://tug.org/mactex/
2. Run the installer (requires ~4GB disk space)
3. Restart your terminal
4. Verify: run `pdflatex --version`

## Option 2: Install Docker Desktop
1. Download from: https://docker.com/products/docker-desktop
2. Install and start Docker Desktop
3. Wait for Docker to fully start (whale icon in menu bar)

After installing either option, restart Aura to detect the compiler.
"""


class UnifiedLatex:
    """
    Unified LaTeX compilation service.

    Automatically selects the best available backend.
    Priority: Local TeX > Tectonic > Docker

    Local TeX is preferred because:
    - Better compatibility with images and complex packages
    - Faster compilation
    - Tectonic has issues with relative image paths
    """

    def __init__(self):
        self.tectonic_latex: TectonicLatex = get_tectonic_latex()
        self.local_latex: LocalLatex = get_local_latex()
        self.docker_latex: DockerLatex = get_docker_latex()
        self._preferred_backend: CompilationBackend = "auto"

    def set_preferred_backend(self, backend: CompilationBackend) -> None:
        """Set the preferred compilation backend."""
        self._preferred_backend = backend

    def get_status(self) -> dict:
        """Get status of available backends."""
        return {
            "tectonic_available": self.tectonic_latex.is_available(),
            "tectonic_version": self.tectonic_latex.get_version() if self.tectonic_latex.is_available() else None,
            "local_available": self.local_latex.is_available(),
            "local_version": self.local_latex.get_version() if self.local_latex.is_available() else None,
            "docker_available": self.docker_latex.is_available(),
            "preferred_backend": self._preferred_backend,
            "active_backend": self._get_active_backend(),
        }

    def _get_active_backend(self) -> Optional[str]:
        """Determine which backend will be used."""
        if self._preferred_backend == "tectonic":
            return "tectonic" if self.tectonic_latex.is_available() else None
        elif self._preferred_backend == "local":
            return "local" if self.local_latex.is_available() else None
        elif self._preferred_backend == "docker":
            return "docker" if self.docker_latex.is_available() else None
        else:  # auto - prefer local, then docker, then tectonic
            if self.local_latex.is_available():
                return "local"
            elif self.docker_latex.is_available():
                return "docker"
            elif self.tectonic_latex.is_available():
                return "tectonic"
            return None

    def is_available(self) -> bool:
        """Check if any compilation backend is available."""
        return (
            self.tectonic_latex.is_available() or
            self.local_latex.is_available() or
            self.docker_latex.is_available()
        )

    async def compile(
        self,
        project_path: str,
        main_file: str = "main.tex",
        backend: Optional[CompilationBackend] = None,
    ) -> CompileResult:
        """
        Compile a LaTeX project.

        Args:
            project_path: Path to the project directory
            main_file: Name of the main .tex file
            backend: Override backend selection (auto/tectonic/local/docker)

        Returns:
            CompileResult with compilation status
        """
        effective_backend = backend or self._preferred_backend

        # Determine which backend to use
        use_tectonic = False
        use_local = False
        use_docker = False

        if effective_backend == "tectonic":
            use_tectonic = self.tectonic_latex.is_available()
        elif effective_backend == "local":
            use_local = self.local_latex.is_available()
        elif effective_backend == "docker":
            use_docker = self.docker_latex.is_available()
        else:  # auto - prefer local, then docker, then tectonic
            if self.local_latex.is_available():
                use_local = True
            elif self.docker_latex.is_available():
                use_docker = True
            elif self.tectonic_latex.is_available():
                use_tectonic = True

        # Try local TeX first (MacTeX) - best compatibility
        if use_local:
            logger.info("Compiling with local TeX")
            result = await self.local_latex.compile(project_path, main_file)
            return CompileResult(
                success=result.success,
                pdf_path=result.pdf_path,
                log=result.log,
                errors=result.errors,
                warnings=result.warnings,
                error_summary=result.error_summary,
                backend_used="local",
            )

        # Try Docker (full TeX Live, handles images)
        if use_docker:
            logger.info("Compiling with Docker")
            result = await self.docker_latex.compile(project_path, main_file)
            return CompileResult(
                success=result.success,
                pdf_path=result.pdf_path,
                log=result.log_output,  # Docker uses log_output
                errors=[],  # Docker doesn't parse errors separately
                warnings=[],
                error_summary=result.error_summary,
                backend_used="docker",
            )

        # Try Tectonic (bundled, works out of box for simple documents)
        if use_tectonic:
            logger.info("Compiling with Tectonic (bundled)")
            result = await self.tectonic_latex.compile(project_path, main_file)
            return CompileResult(
                success=result.success,
                pdf_path=result.pdf_path,
                log=result.log,
                errors=result.errors,
                warnings=result.warnings,
                error_summary=result.error_summary,
                backend_used="tectonic",
            )

        # No backend available
        logger.error("No LaTeX compiler available")
        return CompileResult(
            success=False,
            error_summary=NO_TEX_AVAILABLE_MESSAGE,
            tex_not_available=True,
        )

    async def check_syntax(
        self,
        project_path: str,
        main_file: str = "main.tex",
        backend: Optional[CompilationBackend] = None,
    ) -> CompileResult:
        """
        Quick syntax check.

        Args:
            project_path: Path to the project directory
            main_file: Name of the main .tex file
            backend: Override backend selection

        Returns:
            CompileResult with syntax check status
        """
        effective_backend = backend or self._preferred_backend

        # Determine which backend to use
        use_tectonic = False
        use_local = False
        use_docker = False

        if effective_backend == "tectonic":
            use_tectonic = self.tectonic_latex.is_available()
        elif effective_backend == "local":
            use_local = self.local_latex.is_available()
        elif effective_backend == "docker":
            use_docker = self.docker_latex.is_available()
        else:  # auto - prefer local, then docker, then tectonic
            if self.local_latex.is_available():
                use_local = True
            elif self.docker_latex.is_available():
                use_docker = True
            elif self.tectonic_latex.is_available():
                use_tectonic = True

        if use_local:
            result = await self.local_latex.check_syntax(project_path, main_file)
            return CompileResult(
                success=result.success,
                log=result.log,
                errors=result.errors,
                error_summary=result.error_summary,
                backend_used="local",
            )

        if use_docker:
            result = await self.docker_latex.check_syntax(project_path, main_file)
            return CompileResult(
                success=result.success,
                log=result.log_output,  # Docker uses log_output
                errors=[],
                error_summary=result.error_summary,
                backend_used="docker",
            )

        if use_tectonic:
            result = await self.tectonic_latex.check_syntax(project_path, main_file)
            return CompileResult(
                success=result.success,
                log=result.log,
                errors=result.errors,
                error_summary=result.error_summary,
                backend_used="tectonic",
            )

        return CompileResult(
            success=False,
            error_summary=NO_TEX_AVAILABLE_MESSAGE,
            tex_not_available=True,
        )


# Singleton instance
_unified_latex: Optional[UnifiedLatex] = None


def get_unified_latex() -> UnifiedLatex:
    """Get or create the singleton UnifiedLatex instance."""
    global _unified_latex
    if _unified_latex is None:
        _unified_latex = UnifiedLatex()
    return _unified_latex
