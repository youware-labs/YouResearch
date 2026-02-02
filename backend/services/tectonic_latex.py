"""
Tectonic LaTeX compilation service.

Tectonic is a modern TeX engine that:
- Downloads packages on-demand
- Compiles in a single pass (handles references automatically)
- Produces PDFs directly
- Is bundled with the application

This is the primary compilation method for new users without
MacTeX or Docker installed.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TectonicCompileResult:
    """Result of a Tectonic compilation."""
    success: bool
    pdf_path: Optional[str] = None
    log: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_summary: Optional[str] = None


class TectonicLatex:
    """
    LaTeX compilation service using bundled Tectonic.

    Tectonic is a modern, self-contained TeX engine that downloads
    packages on-demand and handles multiple compilation passes
    automatically.
    """

    def __init__(self):
        self.tectonic_path: Optional[str] = None
        self.available = False
        self._detect_tectonic()

    def _detect_tectonic(self) -> None:
        """Detect bundled Tectonic binary."""
        import shutil

        possible_paths = []

        # Check if running from PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running as bundled executable
            bundle_dir = Path(sys._MEIPASS)
            possible_paths.append(bundle_dir / "bin" / "tectonic")

            # Also check Resources directory (macOS app bundle)
            exe_dir = Path(sys.executable).parent
            possible_paths.append(exe_dir.parent / "Resources" / "backend" / "bin" / "tectonic")
        else:
            # Development mode - check relative to this file
            possible_paths.append(Path(__file__).parent.parent / "bin" / "tectonic")

        for path in possible_paths:
            if path.exists() and os.access(str(path), os.X_OK):
                self.tectonic_path = str(path)
                self.available = True
                logger.info(f"Tectonic found at: {self.tectonic_path}")
                return

        # Also check PATH as fallback
        system_tectonic = shutil.which("tectonic")
        if system_tectonic:
            self.tectonic_path = system_tectonic
            self.available = True
            logger.info(f"Tectonic found in PATH: {self.tectonic_path}")
            return

        logger.warning("Tectonic not found")

    def is_available(self) -> bool:
        """Check if Tectonic is available."""
        return self.available

    def get_version(self) -> Optional[str]:
        """Get Tectonic version string."""
        if not self.tectonic_path:
            return None

        try:
            import subprocess
            result = subprocess.run(
                [self.tectonic_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    async def compile(
        self,
        project_path: str,
        main_file: str = "main.tex",
    ) -> TectonicCompileResult:
        """
        Compile a LaTeX project using Tectonic.

        Tectonic automatically:
        - Handles multiple passes for references
        - Downloads required packages
        - Runs bibtex if needed

        Args:
            project_path: Path to the project directory
            main_file: Name of the main .tex file

        Returns:
            TectonicCompileResult with compilation status and output
        """
        if not self.available:
            return TectonicCompileResult(
                success=False,
                error_summary="Tectonic is not available",
            )

        project_dir = Path(project_path)
        tex_file = project_dir / main_file

        if not tex_file.exists():
            return TectonicCompileResult(
                success=False,
                error_summary=f"File not found: {main_file}",
            )

        # Get the base name without extension
        base_name = main_file.rsplit(".", 1)[0]
        full_log = ""

        try:
            logger.info(f"Compiling with Tectonic: {main_file}")

            # Tectonic command (V1 interface):
            # --keep-logs: Keep log files for debugging
            # --synctex: Generate SyncTeX data
            # Note: V1 interface has better local file/image handling than V2 (-X compile)
            process = await asyncio.create_subprocess_exec(
                self.tectonic_path,
                "--keep-logs",
                "--synctex",
                main_file,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 minute timeout (first run may download packages)
            )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")
            full_log = output + "\n" + error_output

            # Check if PDF was created
            pdf_path = project_dir / f"{base_name}.pdf"

            if pdf_path.exists() and process.returncode == 0:
                # Parse log for warnings
                warnings = self._parse_warnings(full_log)

                return TectonicCompileResult(
                    success=True,
                    pdf_path=str(pdf_path),
                    log=full_log,
                    warnings=warnings,
                )
            else:
                # Parse errors from log
                errors = self._parse_errors(full_log)
                error_summary = errors[0] if errors else "Compilation failed"

                return TectonicCompileResult(
                    success=False,
                    log=full_log,
                    errors=errors,
                    error_summary=error_summary,
                )

        except asyncio.TimeoutError:
            return TectonicCompileResult(
                success=False,
                log=full_log,
                error_summary="Compilation timed out (5 minutes)",
            )
        except Exception as e:
            logger.error(f"Tectonic compilation error: {e}")
            return TectonicCompileResult(
                success=False,
                log=full_log,
                error_summary=str(e),
            )

    def _parse_errors(self, log: str) -> list[str]:
        """Extract error messages from Tectonic log."""
        errors = []
        lines = log.split("\n")

        for i, line in enumerate(lines):
            # Tectonic error patterns
            if line.startswith("error:") or "error:" in line.lower():
                errors.append(line.strip())
            elif line.startswith("!") or ":error:" in line.lower():
                # LaTeX-style errors
                context = "\n".join(lines[i:i+3])
                errors.append(context.strip())

        return errors[:5]  # Return max 5 errors

    def _parse_warnings(self, log: str) -> list[str]:
        """Extract warnings from Tectonic log."""
        warnings = []

        warning_patterns = [
            "warning:",
            "LaTeX Warning:",
            "Package warning:",
            "Overfull \\hbox",
            "Underfull \\hbox",
        ]

        for line in log.split("\n"):
            for pattern in warning_patterns:
                if pattern.lower() in line.lower():
                    warnings.append(line.strip())
                    break

        return warnings[:10]  # Return max 10 warnings

    async def check_syntax(
        self,
        project_path: str,
        main_file: str = "main.tex",
    ) -> TectonicCompileResult:
        """
        Quick syntax check using Tectonic's pass-through mode.

        Note: Tectonic doesn't have a dedicated syntax-check mode,
        so this just does a regular compile.
        """
        return await self.compile(project_path, main_file)


# Singleton instance
_tectonic_latex: Optional[TectonicLatex] = None


def get_tectonic_latex() -> TectonicLatex:
    """Get or create the singleton TectonicLatex instance."""
    global _tectonic_latex
    if _tectonic_latex is None:
        _tectonic_latex = TectonicLatex()
    return _tectonic_latex
