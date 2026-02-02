"""
SyncTeX service for PDF-to-source navigation.

Provides functionality to query synctex files and map PDF positions
to source file locations. Supports both local TeX and Docker.
"""

import asyncio
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncTexResult:
    """Result of a SyncTeX query."""
    success: bool
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    error: Optional[str] = None


class SyncTexService:
    """
    Service for querying SyncTeX files.

    Uses the synctex command-line tool (included with TeX distributions)
    to map PDF coordinates to source file locations.

    Supports:
    - Local TeX installation (MacTeX, TeX Live)
    - Docker (aura-texlive container)
    """

    def __init__(self):
        self.synctex_path: Optional[str] = None
        self.use_docker = False
        self.docker_available = False
        self.docker_image: Optional[str] = None
        self._detect_synctex()

    def _detect_synctex(self) -> None:
        """Detect synctex command-line tool (local or Docker)."""
        # Try to find synctex in PATH
        self.synctex_path = shutil.which("synctex")

        if not self.synctex_path:
            # Common paths for TeX installations
            tex_paths = [
                "/usr/local/texlive/2024/bin/universal-darwin",
                "/usr/local/texlive/2023/bin/universal-darwin",
                "/usr/local/texlive/2025/bin/universal-darwin",
                "/usr/local/texlive/2026/bin/universal-darwin",
                "/Library/TeX/texbin",
                "/usr/bin",
                "/usr/local/bin",
            ]

            for path in tex_paths:
                candidate = os.path.join(path, "synctex")
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    self.synctex_path = candidate
                    break

        if self.synctex_path:
            logger.info(f"SyncTeX found (local): {self.synctex_path}")
        else:
            # Check if Docker is available as fallback
            self._check_docker()
            if self.docker_available:
                self.use_docker = True
                logger.info(f"SyncTeX will use Docker ({self.docker_image})")
            else:
                logger.warning("SyncTeX not available (no local TeX or Docker)")

    def _check_docker(self) -> None:
        """Check if Docker with texlive image is available."""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            # Check if image exists (try multiple image names)
            for image_name in ["texlive/texlive:latest-small", "texlive/texlive", "blang/latex:latest"]:
                try:
                    client.images.get(image_name)
                    self.docker_image = image_name
                    self.docker_available = True
                    logger.info(f"Docker image found for SyncTeX: {image_name}")
                    return
                except Exception:
                    continue
            self.docker_available = False
        except Exception as e:
            logger.debug(f"Docker not available for SyncTeX: {e}")
            self.docker_available = False

    def is_available(self) -> bool:
        """Check if synctex is available (local or Docker)."""
        # Re-check Docker if not already using it
        if not self.synctex_path and not self.use_docker:
            self._check_docker()
            if self.docker_available:
                self.use_docker = True
                logger.info("SyncTeX now using Docker (aura-texlive)")
        return self.synctex_path is not None or self.use_docker

    async def view(
        self,
        project_path: str,
        pdf_file: str,
        page: int,
        x: float,
        y: float,
    ) -> SyncTexResult:
        """
        Query synctex to find source location for a PDF position.

        Args:
            project_path: Path to the project directory
            pdf_file: Name of the PDF file (e.g., "main.pdf")
            page: Page number (1-indexed)
            x: X coordinate in PDF points (72 points = 1 inch)
            y: Y coordinate in PDF points (origin at bottom-left)

        Returns:
            SyncTexResult with source file and line number
        """
        project_dir = Path(project_path)
        pdf_path = project_dir / pdf_file

        # Check if synctex file exists
        synctex_file = pdf_path.with_suffix(".synctex.gz")
        if not synctex_file.exists():
            # Try without .gz
            synctex_file = pdf_path.with_suffix(".synctex")
            if not synctex_file.exists():
                return SyncTexResult(
                    success=False,
                    error="SyncTeX file not found. Please recompile the document."
                )

        if self.use_docker:
            result = await self._view_docker(project_dir, pdf_file, page, x, y)
        elif self.synctex_path:
            result = await self._view_local(project_dir, pdf_file, page, x, y)
        else:
            # Try to detect Docker if not available yet
            self._check_docker()
            if self.docker_available:
                self.use_docker = True
                logger.info("SyncTeX now using Docker (detected on demand)")
                result = await self._view_docker(project_dir, pdf_file, page, x, y)
            else:
                return SyncTexResult(
                    success=False,
                    error="SyncTeX not available (no local TeX or Docker)"
                )

        # If synctex returned column=0, estimate column from x-position
        # Typical LaTeX document has ~1 inch left margin (72pt) and ~6pt per character
        if result.success and (result.column is None or result.column == 0):
            # Estimate: subtract left margin (~72pt), divide by avg char width (~6pt)
            # This gives a rough character position
            left_margin = 72  # ~1 inch default margin
            char_width = 6    # ~6pt per character at 10pt font
            estimated_col = max(1, int((x - left_margin) / char_width) + 1)
            result.column = estimated_col
            logger.debug(f"Estimated column from x={x:.1f}: col={estimated_col}")

        return result

    async def _view_local(
        self,
        project_dir: Path,
        pdf_file: str,
        page: int,
        x: float,
        y: float,
    ) -> SyncTexResult:
        """Run synctex using local installation."""
        try:
            # synctex edit: PDF → source (backwards synchronization)
            # -o page:x:y:file where x,y are from top-left corner
            process = await asyncio.create_subprocess_exec(
                self.synctex_path,
                "edit",
                "-o", f"{page}:{x:.2f}:{y:.2f}:{pdf_file}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=5,
            )

            output = stdout.decode("utf-8", errors="replace")

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
                logger.warning(f"SyncTeX failed: {error_msg}")
                return SyncTexResult(
                    success=False,
                    error=f"SyncTeX query failed: {error_msg}"
                )

            return self._parse_output(output, project_dir)

        except asyncio.TimeoutError:
            return SyncTexResult(
                success=False,
                error="SyncTeX query timed out"
            )
        except Exception as e:
            logger.error(f"SyncTeX error: {e}")
            return SyncTexResult(
                success=False,
                error=str(e)
            )

    async def _view_docker(
        self,
        project_dir: Path,
        pdf_file: str,
        page: int,
        x: float,
        y: float,
    ) -> SyncTexResult:
        """Run synctex using Docker container."""
        try:
            import docker
            client = docker.from_env()

            # synctex edit: PDF → source (backwards synchronization)
            # -o page:x:y:file where x,y are from top-left corner
            cmd = f"synctex edit -o '{page}:{x:.2f}:{y:.2f}:{pdf_file}'"

            def _run_container():
                try:
                    output = client.containers.run(
                        self.docker_image,
                        command=f"/bin/bash -c \"{cmd}\"",
                        volumes={str(project_dir): {"bind": "/workspace", "mode": "ro"}},
                        working_dir="/workspace",
                        remove=True,
                        detach=False,
                        stdout=True,
                        stderr=True,
                    )
                    return output.decode("utf-8", errors="replace")
                except docker.errors.ContainerError as e:
                    if e.stderr:
                        return e.stderr.decode("utf-8", errors="replace")
                    return str(e)
                except Exception as e:
                    return f"Docker error: {e}"

            loop = asyncio.get_event_loop()
            output = await asyncio.wait_for(
                loop.run_in_executor(None, _run_container),
                timeout=10,
            )

            return self._parse_output(output, project_dir, docker_mode=True)

        except asyncio.TimeoutError:
            return SyncTexResult(
                success=False,
                error="SyncTeX query timed out (Docker)"
            )
        except Exception as e:
            logger.error(f"SyncTeX Docker error: {e}")
            return SyncTexResult(
                success=False,
                error=str(e)
            )

    def _parse_output(self, output: str, project_dir: Path, docker_mode: bool = False) -> SyncTexResult:
        """Parse synctex view output to extract source location."""
        # Example output:
        # SyncTeX result begin
        # Output:main.pdf
        # Input:/path/to/file.tex
        # Line:42
        # Column:0
        # ...
        # SyncTeX result end

        file_match = re.search(r"Input:(.+)", output)
        line_match = re.search(r"Line:(\d+)", output)
        column_match = re.search(r"Column:(\d+)", output)

        if not file_match or not line_match:
            # No match found - might be clicking on whitespace or graphics
            logger.debug(f"SyncTeX no match in output: {output[:200]}")
            return SyncTexResult(
                success=False,
                error="No source location found for this position"
            )

        # Get the file path
        file_path = file_match.group(1).strip()
        line = int(line_match.group(1))
        column = int(column_match.group(1)) if column_match else 0

        # Convert path to relative
        # In Docker mode, paths are like /workspace/./file.tex
        if docker_mode and file_path.startswith("/workspace/"):
            file_path = file_path[len("/workspace/"):]

        # Remove leading ./
        if file_path.startswith("./"):
            file_path = file_path[2:]

        # Try to make absolute paths relative
        if not docker_mode:
            try:
                file_path_obj = Path(file_path)
                if file_path_obj.is_absolute():
                    file_path = str(file_path_obj.relative_to(project_dir))
            except (ValueError, RuntimeError):
                # If we can't make it relative, use basename
                file_path = Path(file_path).name

        logger.info(f"SyncTeX found: {file_path}:{line}")

        return SyncTexResult(
            success=True,
            file=file_path,
            line=line,
            column=column,
        )


# Singleton instance
_synctex_service: Optional[SyncTexService] = None


def get_synctex_service() -> SyncTexService:
    """Get or create the singleton SyncTexService instance."""
    global _synctex_service
    if _synctex_service is None:
        _synctex_service = SyncTexService()
    return _synctex_service
