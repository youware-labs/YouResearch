"""
Local LaTeX compilation service.

Runs pdflatex directly on the system without Docker.
Requires MacTeX, TeX Live, or similar TeX distribution to be installed.
"""

import asyncio
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LocalCompileResult:
    """Result of a local LaTeX compilation."""
    success: bool
    pdf_path: Optional[str] = None
    log: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_summary: Optional[str] = None


class LocalLatex:
    """
    LaTeX compilation service using local TeX installation.

    Supports MacTeX, TeX Live, MiKTeX, and other TeX distributions.
    """

    def __init__(self):
        self.pdflatex_path: Optional[str] = None
        self.bibtex_path: Optional[str] = None
        self.available = False
        self._detect_tex()

    def _detect_tex(self) -> None:
        """Detect local TeX installation."""
        # Common paths for TeX installations
        tex_paths = [
            "/usr/local/texlive/2024/bin/universal-darwin",  # MacTeX 2024
            "/usr/local/texlive/2023/bin/universal-darwin",  # MacTeX 2023
            "/usr/local/texlive/2025/bin/universal-darwin",  # MacTeX 2025
            "/usr/local/texlive/2026/bin/universal-darwin",  # MacTeX 2026
            "/Library/TeX/texbin",  # MacTeX symlink
            "/usr/bin",  # Linux system TeX
            "/usr/local/bin",  # Homebrew TeX
        ]

        # Try to find pdflatex
        self.pdflatex_path = shutil.which("pdflatex")

        if not self.pdflatex_path:
            # Search in common paths
            for path in tex_paths:
                candidate = os.path.join(path, "pdflatex")
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    self.pdflatex_path = candidate
                    break

        if self.pdflatex_path:
            self.available = True
            # Also find bibtex
            bibtex_dir = os.path.dirname(self.pdflatex_path)
            bibtex_candidate = os.path.join(bibtex_dir, "bibtex")
            if os.path.isfile(bibtex_candidate):
                self.bibtex_path = bibtex_candidate
            else:
                self.bibtex_path = shutil.which("bibtex")

            logger.info(f"Local TeX found: pdflatex={self.pdflatex_path}, bibtex={self.bibtex_path}")
        else:
            logger.warning("No local TeX installation found")

    def is_available(self) -> bool:
        """Check if local TeX is available."""
        return self.available

    def get_version(self) -> Optional[str]:
        """Get TeX version string."""
        if not self.pdflatex_path:
            return None

        try:
            import subprocess
            result = subprocess.run(
                [self.pdflatex_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # First line usually contains version
                return result.stdout.split("\n")[0]
        except Exception:
            pass
        return None

    async def compile(
        self,
        project_path: str,
        main_file: str = "main.tex",
        runs: int = 2,
    ) -> LocalCompileResult:
        """
        Compile a LaTeX project using local pdflatex.

        Args:
            project_path: Path to the project directory
            main_file: Name of the main .tex file
            runs: Number of pdflatex runs (for references)

        Returns:
            LocalCompileResult with compilation status and output
        """
        if not self.available:
            return LocalCompileResult(
                success=False,
                error_summary="Local TeX is not installed",
            )

        project_dir = Path(project_path)
        tex_file = project_dir / main_file

        if not tex_file.exists():
            return LocalCompileResult(
                success=False,
                error_summary=f"File not found: {main_file}",
            )

        # Get the base name without extension
        base_name = main_file.rsplit(".", 1)[0]

        errors: list[str] = []
        warnings: list[str] = []
        full_log = ""

        try:
            # Run pdflatex multiple times for references
            for run_num in range(runs):
                logger.info(f"pdflatex run {run_num + 1}/{runs}")

                process = await asyncio.create_subprocess_exec(
                    self.pdflatex_path,
                    "-synctex=1",  # Generate .synctex.gz for PDF-to-source navigation
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-file-line-error",
                    main_file,
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, "PATH": f"{os.path.dirname(self.pdflatex_path)}:{os.environ.get('PATH', '')}"},
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=120,  # 2 minute timeout
                )

                output = stdout.decode("utf-8", errors="replace")
                full_log += f"\n=== pdflatex run {run_num + 1} ===\n{output}"

                if stderr:
                    full_log += f"\nSTDERR: {stderr.decode('utf-8', errors='replace')}"

                # Run bibtex after first pdflatex if .bib files exist
                if run_num == 0 and self.bibtex_path:
                    bib_files = list(project_dir.glob("*.bib"))
                    aux_file = project_dir / f"{base_name}.aux"

                    if bib_files and aux_file.exists():
                        logger.info("Running bibtex")
                        bib_process = await asyncio.create_subprocess_exec(
                            self.bibtex_path,
                            base_name,
                            cwd=str(project_dir),
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env={**os.environ, "PATH": f"{os.path.dirname(self.bibtex_path)}:{os.environ.get('PATH', '')}"},
                        )

                        bib_stdout, bib_stderr = await asyncio.wait_for(
                            bib_process.communicate(),
                            timeout=30,
                        )

                        full_log += f"\n=== bibtex ===\n{bib_stdout.decode('utf-8', errors='replace')}"

            # Check if PDF was created
            pdf_path = project_dir / f"{base_name}.pdf"

            if pdf_path.exists():
                # Parse log for warnings
                warnings = self._parse_warnings(full_log)

                return LocalCompileResult(
                    success=True,
                    pdf_path=str(pdf_path),
                    log=full_log,
                    warnings=warnings,
                )
            else:
                # Parse errors from log
                errors = self._parse_errors(full_log)
                error_summary = errors[0] if errors else "Compilation failed - no PDF produced"

                return LocalCompileResult(
                    success=False,
                    log=full_log,
                    errors=errors,
                    error_summary=error_summary,
                )

        except asyncio.TimeoutError:
            return LocalCompileResult(
                success=False,
                log=full_log,
                error_summary="Compilation timed out (2 minutes)",
            )
        except Exception as e:
            logger.error(f"Compilation error: {e}")
            return LocalCompileResult(
                success=False,
                log=full_log,
                error_summary=str(e),
            )

    def _parse_errors(self, log: str) -> list[str]:
        """Extract error messages from LaTeX log."""
        errors = []
        lines = log.split("\n")

        for i, line in enumerate(lines):
            # Look for error patterns
            if line.startswith("!") or ":error:" in line.lower():
                # Get context (next few lines)
                context = "\n".join(lines[i:i+3])
                errors.append(context.strip())
            elif "Fatal error" in line or "Emergency stop" in line:
                errors.append(line.strip())

        return errors[:5]  # Return max 5 errors

    def _parse_warnings(self, log: str) -> list[str]:
        """Extract warnings from LaTeX log."""
        warnings = []

        warning_patterns = [
            "LaTeX Warning:",
            "Package warning:",
            "Overfull \\hbox",
            "Underfull \\hbox",
        ]

        for line in log.split("\n"):
            for pattern in warning_patterns:
                if pattern in line:
                    warnings.append(line.strip())
                    break

        return warnings[:10]  # Return max 10 warnings

    async def check_syntax(
        self,
        project_path: str,
        main_file: str = "main.tex",
    ) -> LocalCompileResult:
        """
        Quick syntax check without full compilation.

        Uses -draftmode for faster checking.
        """
        if not self.available:
            return LocalCompileResult(
                success=False,
                error_summary="Local TeX is not installed",
            )

        project_dir = Path(project_path)
        tex_file = project_dir / main_file

        if not tex_file.exists():
            return LocalCompileResult(
                success=False,
                error_summary=f"File not found: {main_file}",
            )

        try:
            process = await asyncio.create_subprocess_exec(
                self.pdflatex_path,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-draftmode",  # Faster, no PDF output
                main_file,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PATH": f"{os.path.dirname(self.pdflatex_path)}:{os.environ.get('PATH', '')}"},
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30,
            )

            output = stdout.decode("utf-8", errors="replace")

            if process.returncode == 0:
                return LocalCompileResult(
                    success=True,
                    log=output,
                )
            else:
                errors = self._parse_errors(output)
                return LocalCompileResult(
                    success=False,
                    log=output,
                    errors=errors,
                    error_summary=errors[0] if errors else "Syntax check failed",
                )

        except asyncio.TimeoutError:
            return LocalCompileResult(
                success=False,
                error_summary="Syntax check timed out",
            )
        except Exception as e:
            return LocalCompileResult(
                success=False,
                error_summary=str(e),
            )


# Singleton instance
_local_latex: Optional[LocalLatex] = None


def get_local_latex() -> LocalLatex:
    """Get or create the singleton LocalLatex instance."""
    global _local_latex
    if _local_latex is None:
        _local_latex = LocalLatex()
    return _local_latex
