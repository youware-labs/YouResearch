"""
Docker Setup Service

Handles guided Docker Desktop installation:
- Status checking (installed, running, image pulled)
- Downloading Docker.dmg
- Opening installer
- Pulling TeX image
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import platform

logger = logging.getLogger(__name__)


class DockerStatus(str, Enum):
    """Docker installation status."""
    NOT_INSTALLED = "not_installed"
    INSTALLED_NOT_RUNNING = "installed_not_running"
    RUNNING_NO_IMAGE = "running_no_image"
    READY = "ready"


@dataclass
class DockerSetupStatus:
    """Full Docker setup status."""
    status: DockerStatus
    docker_installed: bool = False
    docker_running: bool = False
    image_pulled: bool = False
    image_name: str = "aura-texlive"
    download_progress: float = 0.0  # 0-100
    download_path: Optional[str] = None
    error: Optional[str] = None


class DockerSetupService:
    """
    Service for guided Docker Desktop installation.

    Flow:
    1. Check status
    2. Download Docker.dmg if needed
    3. Open installer for user
    4. Poll until Docker is running
    5. Pull TeX image
    """

    DOCKER_DMG_URL = "https://desktop.docker.com/mac/main/arm64/Docker.dmg"
    DOCKER_DMG_URL_INTEL = "https://desktop.docker.com/mac/main/amd64/Docker.dmg"

    # Use pre-built images from Docker Hub (much faster than building)
    IMAGE_NAME = "texlive/texlive:latest-small"  # ~1GB, good balance
    FALLBACK_IMAGE = "blang/latex:latest"  # ~800MB, even smaller

    # Common paths where Docker CLI might be installed
    DOCKER_PATHS = [
        "/usr/local/bin/docker",
        "/opt/homebrew/bin/docker",
        "/usr/bin/docker",
        "/Applications/Docker.app/Contents/Resources/bin/docker",
    ]

    def __init__(self):
        self._download_progress: float = 0.0
        self._download_path: Optional[str] = None
        self._downloading: bool = False
        self._pull_progress: float = 0.0
        self._pulling: bool = False
        self._docker_path: Optional[str] = None

    def _find_docker_cli(self) -> Optional[str]:
        """Find the Docker CLI executable path."""
        if self._docker_path:
            return self._docker_path

        # Try shutil.which first
        docker_path = shutil.which("docker")
        if docker_path:
            self._docker_path = docker_path
            return docker_path

        # Search common paths
        for path in self.DOCKER_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                self._docker_path = path
                logger.info(f"Found Docker CLI at: {path}")
                return path

        return None

    def get_docker_dmg_url(self) -> str:
        """Get the appropriate Docker DMG URL for this architecture."""
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            return self.DOCKER_DMG_URL
        else:
            return self.DOCKER_DMG_URL_INTEL

    def is_docker_installed(self) -> bool:
        """Check if Docker is installed."""
        # Check for Docker.app
        docker_app = Path("/Applications/Docker.app")
        if docker_app.exists():
            return True

        # Check for docker CLI
        docker_path = self._find_docker_cli()
        return docker_path is not None

    def is_docker_running(self) -> bool:
        """Check if Docker daemon is running."""
        docker_path = self._find_docker_cli()
        if not docker_path:
            logger.warning("Docker CLI not found in PATH or common locations")
            return False

        try:
            result = subprocess.run(
                [docker_path, "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Docker info check failed: {e}")
            return False

    def is_image_pulled(self) -> bool:
        """Check if a TeX image is available (primary or fallback)."""
        if not self.is_docker_running():
            return False

        docker_path = self._find_docker_cli()
        if not docker_path:
            return False

        # Check for either the primary or fallback image
        for image_name in [self.IMAGE_NAME, self.FALLBACK_IMAGE]:
            try:
                result = subprocess.run(
                    [docker_path, "images", "-q", image_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.stdout.strip():
                    return True
            except Exception:
                continue
        return False

    def get_status(self) -> DockerSetupStatus:
        """Get the full Docker setup status."""
        docker_installed = self.is_docker_installed()
        docker_running = self.is_docker_running() if docker_installed else False
        image_pulled = self.is_image_pulled() if docker_running else False

        if not docker_installed:
            status = DockerStatus.NOT_INSTALLED
        elif not docker_running:
            status = DockerStatus.INSTALLED_NOT_RUNNING
        elif not image_pulled:
            status = DockerStatus.RUNNING_NO_IMAGE
        else:
            status = DockerStatus.READY

        return DockerSetupStatus(
            status=status,
            docker_installed=docker_installed,
            docker_running=docker_running,
            image_pulled=image_pulled,
            image_name=self.IMAGE_NAME,
            download_progress=self._download_progress,
            download_path=self._download_path,
        )

    async def download_docker(self) -> DockerSetupStatus:
        """
        Download Docker.dmg to Downloads folder.
        Returns status with download path.
        """
        if self._downloading:
            return DockerSetupStatus(
                status=DockerStatus.NOT_INSTALLED,
                download_progress=self._download_progress,
                error="Download already in progress",
            )

        self._downloading = True
        self._download_progress = 0.0

        try:
            downloads_dir = Path.home() / "Downloads"
            download_path = downloads_dir / "Docker.dmg"

            # Use curl for download with progress
            url = self.get_docker_dmg_url()
            logger.info(f"Downloading Docker from {url}")

            process = await asyncio.create_subprocess_exec(
                "curl", "-L", "-o", str(download_path),
                "--progress-bar", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode == 0 and download_path.exists():
                self._download_path = str(download_path)
                self._download_progress = 100.0
                logger.info(f"Docker downloaded to {download_path}")

                return DockerSetupStatus(
                    status=DockerStatus.NOT_INSTALLED,
                    download_progress=100.0,
                    download_path=str(download_path),
                )
            else:
                error = stderr.decode() if stderr else "Download failed"
                return DockerSetupStatus(
                    status=DockerStatus.NOT_INSTALLED,
                    error=error,
                )

        except Exception as e:
            logger.error(f"Docker download error: {e}")
            return DockerSetupStatus(
                status=DockerStatus.NOT_INSTALLED,
                error=str(e),
            )

        finally:
            self._downloading = False

    async def open_installer(self) -> DockerSetupStatus:
        """
        Open the Docker.dmg installer.
        """
        download_path = self._download_path or str(Path.home() / "Downloads" / "Docker.dmg")

        if not Path(download_path).exists():
            return DockerSetupStatus(
                status=DockerStatus.NOT_INSTALLED,
                error="Docker.dmg not found. Please download first.",
            )

        try:
            # Mount the DMG
            logger.info(f"Opening {download_path}")
            process = await asyncio.create_subprocess_exec(
                "open", download_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            return DockerSetupStatus(
                status=DockerStatus.NOT_INSTALLED,
                download_path=download_path,
            )

        except Exception as e:
            logger.error(f"Error opening installer: {e}")
            return DockerSetupStatus(
                status=DockerStatus.NOT_INSTALLED,
                error=str(e),
            )

    async def start_docker(self) -> DockerSetupStatus:
        """
        Try to start Docker Desktop.
        """
        docker_app = Path("/Applications/Docker.app")

        if not docker_app.exists():
            return DockerSetupStatus(
                status=DockerStatus.NOT_INSTALLED,
                error="Docker.app not found in Applications",
            )

        try:
            logger.info("Starting Docker Desktop")
            process = await asyncio.create_subprocess_exec(
                "open", "-a", "Docker",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            return self.get_status()

        except Exception as e:
            logger.error(f"Error starting Docker: {e}")
            return DockerSetupStatus(
                status=DockerStatus.INSTALLED_NOT_RUNNING,
                docker_installed=True,
                error=str(e),
            )

    async def pull_image(self, dockerfile_path: Optional[str] = None) -> DockerSetupStatus:
        """
        Pull the TeX image from Docker Hub.
        """
        if not self.is_docker_running():
            return DockerSetupStatus(
                status=DockerStatus.INSTALLED_NOT_RUNNING,
                docker_installed=True,
                error="Docker is not running",
            )

        docker_path = self._find_docker_cli()
        if not docker_path:
            return DockerSetupStatus(
                status=DockerStatus.RUNNING_NO_IMAGE,
                docker_installed=True,
                docker_running=True,
                error="Docker CLI not found",
            )

        self._pulling = True
        self._pull_progress = 0.0

        try:
            # Try to pull the primary image first
            logger.info(f"Pulling Docker image: {self.IMAGE_NAME}")

            process = await asyncio.create_subprocess_exec(
                docker_path, "pull", self.IMAGE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                self._pull_progress = 100.0
                logger.info(f"Successfully pulled {self.IMAGE_NAME}")
                return self.get_status()
            else:
                # Try fallback image
                logger.warning(f"Failed to pull {self.IMAGE_NAME}, trying fallback: {self.FALLBACK_IMAGE}")

                process = await asyncio.create_subprocess_exec(
                    docker_path, "pull", self.FALLBACK_IMAGE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    self._pull_progress = 100.0
                    logger.info(f"Successfully pulled fallback image {self.FALLBACK_IMAGE}")
                    return self.get_status()
                else:
                    error = stderr.decode() if stderr else "Pull failed"
                    return DockerSetupStatus(
                        status=DockerStatus.RUNNING_NO_IMAGE,
                        docker_installed=True,
                        docker_running=True,
                        error=f"Failed to pull images: {error}",
                    )

        except Exception as e:
            logger.error(f"Error pulling image: {e}")
            return DockerSetupStatus(
                status=DockerStatus.RUNNING_NO_IMAGE,
                docker_installed=True,
                docker_running=True,
                error=str(e),
            )

        finally:
            self._pulling = False


# Singleton instance
_docker_setup: Optional[DockerSetupService] = None


def get_docker_setup() -> DockerSetupService:
    """Get or create the singleton DockerSetupService instance."""
    global _docker_setup
    if _docker_setup is None:
        _docker_setup = DockerSetupService()
    return _docker_setup
