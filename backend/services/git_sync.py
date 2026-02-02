"""
Git/Overleaf Sync Service

Provides Git-based synchronization with Overleaf projects.

Overleaf exposes each project as a Git repository that can be cloned,
pulled, and pushed to. This service manages that synchronization.

Usage:
    sync = GitSyncService(project_path)

    # Setup (one-time)
    await sync.setup(overleaf_url, username, password)

    # Regular sync
    status = await sync.get_status()
    await sync.pull()
    await sync.push(commit_message)
"""

import asyncio
import subprocess
import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Synchronization status states."""
    NOT_INITIALIZED = "not_initialized"  # No git repo or no remote
    CLEAN = "clean"  # Up to date with remote
    LOCAL_CHANGES = "local_changes"  # Uncommitted local changes
    AHEAD = "ahead"  # Local commits not pushed
    BEHIND = "behind"  # Remote has new commits
    DIVERGED = "diverged"  # Both local and remote have changes
    CONFLICT = "conflict"  # Merge conflict detected
    ERROR = "error"  # Error state


@dataclass
class SyncInfo:
    """Information about sync state."""
    status: SyncStatus
    is_git_repo: bool = False
    has_remote: bool = False
    remote_url: Optional[str] = None
    branch: str = "master"
    commits_ahead: int = 0
    commits_behind: int = 0
    uncommitted_files: list[str] = field(default_factory=list)
    last_sync: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "is_git_repo": self.is_git_repo,
            "has_remote": self.has_remote,
            "remote_url": self.remote_url,
            "branch": self.branch,
            "commits_ahead": self.commits_ahead,
            "commits_behind": self.commits_behind,
            "uncommitted_files": self.uncommitted_files,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "error_message": self.error_message,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    operation: str  # "pull", "push", "setup"
    message: str
    files_changed: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "operation": self.operation,
            "message": self.message,
            "files_changed": self.files_changed,
            "conflicts": self.conflicts,
        }


# Config file for storing sync settings
SYNC_CONFIG_FILE = ".aura/sync.json"

# Gitignore patterns for LaTeX projects (shouldn't sync to Overleaf)
GITIGNORE_PATTERNS = [
    "# Aura local config",
    ".aura/",
    "",
    "# Compiled output (Overleaf compiles its own)",
    "*.pdf",
    "",
    "# LaTeX auxiliary files",
    "*.aux",
    "*.bbl",
    "*.blg",
    "*.log",
    "*.out",
    "*.toc",
    "*.lof",
    "*.lot",
    "*.fls",
    "*.fdb_latexmk",
    "*.synctex.gz",
    "*.synctex(busy)",
    "*.run.xml",
    "*.bcf",
    "*.nav",
    "*.snm",
    "*.vrb",
    "*.idx",
    "*.ilg",
    "*.ind",
    "*.glo",
    "*.gls",
    "*.glg",
    "*.xdv",
    "",
    "# System files",
    ".DS_Store",
    "Thumbs.db",
]


class GitSyncService:
    """
    Service for synchronizing LaTeX projects with Overleaf via Git.

    Overleaf provides a Git interface for each project:
    - Clone URL: https://git.overleaf.com/<project_id>
    - Requires Overleaf credentials (email + password or token)
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.config_path = self.project_path / SYNC_CONFIG_FILE

    async def _run_git(
        self,
        *args: str,
        check: bool = True,
        capture_output: bool = True,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess:
        """Run a git command in the project directory."""
        cmd = ["git", *args]
        logger.debug(f"Running: {' '.join(cmd)} with timeout={timeout}")

        # Environment to prevent interactive prompts
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"  # Disable terminal prompts
        env["GIT_ASKPASS"] = "echo"  # Return empty for password prompts
        env["GIT_CONFIG_GLOBAL"] = "/dev/null"  # Ignore global git config
        env["GIT_CONFIG_SYSTEM"] = "/dev/null"  # Ignore system git config

        try:
            # Use asyncio.create_subprocess_exec for proper async subprocess
            logger.debug(f"Creating subprocess in {self.project_path}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.project_path),
                stdin=asyncio.subprocess.DEVNULL,  # Prevent stdin blocking
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                env=env,
            )
            logger.debug(f"Subprocess created, pid={process.pid}")

            try:
                logger.debug(f"Waiting for process with timeout={timeout}")
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                stdout_str = stdout.decode() if stdout else ""
                stderr_str = stderr.decode() if stderr else ""
                returncode = process.returncode or 0
                logger.debug(f"Process completed: returncode={returncode}")
            except asyncio.TimeoutError:
                logger.warning(f"Command timed out after {timeout}s, killing process")
                process.kill()
                await process.wait()
                return subprocess.CompletedProcess(cmd, 1, "", "Command timed out")

        except Exception as e:
            logger.error(f"Git command error: {e}")
            return subprocess.CompletedProcess(cmd, 1, "", str(e))

        result = subprocess.CompletedProcess(cmd, returncode, stdout_str, stderr_str)

        if check and result.returncode != 0:
            logger.error(f"Git command failed: {result.stderr}")

        return result

    def _load_config(self) -> dict:
        """Load sync configuration from project."""
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load sync config: {e}")
            return {}

    def _save_config(self, config: dict) -> None:
        """Save sync configuration to project."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2, default=str)

    def _ensure_gitignore(self) -> None:
        """Ensure .gitignore has proper patterns for LaTeX auxiliary files."""
        gitignore_path = self.project_path / ".gitignore"
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            # Check if we need to add patterns (use *.pdf as marker for updated patterns)
            if "*.pdf" not in content:
                with open(gitignore_path, "a") as f:
                    f.write("\n" + "\n".join(GITIGNORE_PATTERNS) + "\n")
        else:
            gitignore_path.write_text("\n".join(GITIGNORE_PATTERNS) + "\n")

    async def _remove_ignored_from_cache(self) -> None:
        """Remove files that are in .gitignore but still tracked by git."""
        # Get list of tracked files that match gitignore patterns
        patterns_to_check = [
            "*.pdf", "*.aux", "*.bbl", "*.blg", "*.log", "*.out", "*.toc",
            "*.lof", "*.lot", "*.fls", "*.fdb_latexmk", "*.synctex.gz",
            "*.synctex(busy)", "*.run.xml", "*.bcf", "*.nav", "*.snm",
            "*.vrb", "*.idx", "*.ilg", "*.ind", "*.glo", "*.gls", "*.glg",
            "*.xdv", ".aura/*", ".DS_Store"
        ]

        for pattern in patterns_to_check:
            # Remove from git cache (but keep local files)
            await self._run_git(
                "rm", "-r", "--cached", "--ignore-unmatch", pattern,
                check=False
            )

    async def is_git_repo(self) -> bool:
        """Check if project is a git repository."""
        git_dir = self.project_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    async def get_remote_url(self) -> Optional[str]:
        """Get the Overleaf remote URL if configured."""
        result = await self._run_git("remote", "get-url", "origin", check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    async def get_remote_branch(self) -> str:
        """
        Get the remote's default branch name.

        Tries to detect the remote's HEAD, falls back to checking common names.
        Returns 'master' as fallback if detection fails.
        """
        # First try to get the remote's HEAD reference
        result = await self._run_git("symbolic-ref", "refs/remotes/origin/HEAD", check=False)
        if result.returncode == 0:
            # Returns something like "refs/remotes/origin/main"
            ref = result.stdout.strip()
            if ref:
                return ref.split("/")[-1]

        # If that fails, check which remote branches exist
        result = await self._run_git("branch", "-r", check=False)
        if result.returncode == 0:
            branches = result.stdout.strip().split("\n")
            for branch in branches:
                branch = branch.strip()
                # Check for origin/main first (newer convention)
                if branch == "origin/main" or branch.endswith("origin/main"):
                    return "main"
                if branch == "origin/master" or branch.endswith("origin/master"):
                    return "master"

        # Default fallback
        return "master"

    async def get_status(self, fetch: bool = True) -> SyncInfo:
        """
        Get comprehensive sync status.

        Args:
            fetch: If True, fetches from remote first (slower but accurate).
                   If False, uses cached remote info (faster for local-only checks).
        """
        info = SyncInfo(status=SyncStatus.NOT_INITIALIZED)

        # Check if git repo
        if not await self.is_git_repo():
            return info

        info.is_git_repo = True

        # Get remote URL
        info.remote_url = await self.get_remote_url()
        info.has_remote = bool(info.remote_url)

        if not info.has_remote:
            info.status = SyncStatus.NOT_INITIALIZED
            return info

        # Remote is configured - default to CLEAN until we find otherwise
        info.status = SyncStatus.CLEAN

        # Get current branch
        result = await self._run_git("branch", "--show-current", check=False)
        if result.returncode == 0:
            info.branch = result.stdout.strip() or "master"

        # Check for uncommitted changes
        result = await self._run_git("status", "--porcelain", check=False)
        if result.returncode == 0 and result.stdout.strip():
            info.uncommitted_files = [
                line[3:] for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            info.status = SyncStatus.LOCAL_CHANGES
            return info

        # Fetch to check remote status (skip if fetch=False for speed)
        if fetch:
            await self._run_git("fetch", "origin", check=False, timeout=60)

        # Check ahead/behind
        result = await self._run_git(
            "rev-list", "--left-right", "--count",
            f"HEAD...origin/{info.branch}",
            check=False,
        )

        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                info.commits_ahead = int(parts[0])
                info.commits_behind = int(parts[1])

                if info.commits_ahead > 0 and info.commits_behind > 0:
                    info.status = SyncStatus.DIVERGED
                elif info.commits_ahead > 0:
                    info.status = SyncStatus.AHEAD
                elif info.commits_behind > 0:
                    info.status = SyncStatus.BEHIND
                else:
                    info.status = SyncStatus.CLEAN

        # Load last sync time from config
        config = self._load_config()
        if "last_sync" in config:
            try:
                info.last_sync = datetime.fromisoformat(config["last_sync"])
            except (ValueError, TypeError):
                pass

        return info

    async def setup(
        self,
        overleaf_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> SyncResult:
        """
        Set up Git sync with Overleaf.

        Args:
            overleaf_url: Overleaf git URL (https://git.overleaf.com/<project_id>)
            username: Overleaf email (optional, will prompt if needed)
            password: Overleaf password or token (optional)

        Returns:
            SyncResult with setup status
        """
        # Clean URL - remove any embedded credentials (e.g., git@ or user:pass@)
        import re
        clean_url = re.sub(r'https://[^@]+@', 'https://', overleaf_url)
        logger.info(f"Setup sync: project={self.project_path}, clean_url={clean_url}")

        # Validate URL
        if not clean_url.startswith("https://git.overleaf.com/"):
            return SyncResult(
                success=False,
                operation="setup",
                message="Invalid Overleaf URL. Expected: https://git.overleaf.com/<project_id>",
            )

        # Build URL with credentials if provided
        auth_url = clean_url
        if password:
            from urllib.parse import quote
            # For Overleaf tokens (start with "olp_"), username must be "git"
            # For regular passwords, use the provided email
            if password.startswith("olp_"):
                auth_username = "git"
            else:
                auth_username = username or "git"
            auth_url = clean_url.replace(
                "https://",
                f"https://{quote(auth_username)}:{quote(password)}@"
            )

        # Initialize git if needed
        if not await self.is_git_repo():
            result = await self._run_git("init", check=False)
            if result.returncode != 0:
                return SyncResult(
                    success=False,
                    operation="setup",
                    message=f"Failed to initialize git: {result.stderr}",
                )

        # Check for existing remote
        existing_remote = await self.get_remote_url()
        if existing_remote:
            # Update existing remote
            result = await self._run_git(
                "remote", "set-url", "origin", auth_url, check=False
            )
        else:
            # Add new remote
            result = await self._run_git(
                "remote", "add", "origin", auth_url, check=False
            )

        if result.returncode != 0:
            return SyncResult(
                success=False,
                operation="setup",
                message=f"Failed to configure remote: {result.stderr}",
            )

        # Try to fetch from remote (use longer timeout for network ops)
        logger.info(f"Fetching from origin...")
        result = await self._run_git("fetch", "origin", check=False, timeout=60)
        logger.info(f"Fetch result: returncode={result.returncode}, stderr={result.stderr[:100] if result.stderr else 'empty'}")
        if result.returncode != 0:
            # Check for auth failure
            if "Authentication failed" in result.stderr or "403" in result.stderr:
                return SyncResult(
                    success=False,
                    operation="setup",
                    message="Authentication failed. Check your Overleaf credentials.",
                )
            return SyncResult(
                success=False,
                operation="setup",
                message=f"Failed to connect to Overleaf: {result.stderr}",
            )

        # Set up tracking branch (detect remote branch after fetch)
        remote_branch = await self.get_remote_branch()
        local_branch = "main" if remote_branch == "main" else "master"

        # Get current local branch
        current_result = await self._run_git("branch", "--show-current", check=False)
        current_branch = current_result.stdout.strip() if current_result.returncode == 0 else ""

        # If no commits yet or branch doesn't match, rename/create the right branch
        if current_branch and current_branch != local_branch:
            await self._run_git("branch", "-m", current_branch, local_branch, check=False)
        elif not current_branch:
            # No commits yet - the branch will be created on first commit
            pass

        # Set upstream tracking
        await self._run_git(
            "branch", f"--set-upstream-to=origin/{remote_branch}", local_branch, check=False
        )

        # Ensure gitignore is set up early to exclude auxiliary files
        self._ensure_gitignore()

        # Save config (without credentials - they're in git config)
        config = self._load_config()
        config["overleaf_url"] = clean_url  # Store clean URL
        config["setup_time"] = datetime.now().isoformat()
        self._save_config(config)

        # Store credentials in git credential helper (more secure)
        if username and password:
            # Configure credential helper to cache
            await self._run_git(
                "config", "credential.helper", "cache --timeout=3600", check=False
            )

        return SyncResult(
            success=True,
            operation="setup",
            message="Successfully connected to Overleaf. You can now sync your project.",
        )

    async def pull(self, filepath: Optional[str] = None) -> SyncResult:
        """
        Pull changes from Overleaf.

        Args:
            filepath: Only commit this file before pulling (optional)

        Returns:
            SyncResult with pull status
        """
        if not await self.is_git_repo():
            return SyncResult(
                success=False,
                operation="pull",
                message="Not a git repository. Run setup first.",
            )

        remote_url = await self.get_remote_url()
        if not remote_url:
            return SyncResult(
                success=False,
                operation="pull",
                message="No remote configured. Run setup first.",
            )

        # Ensure local/auxiliary files are ignored (shouldn't sync to Overleaf)
        self._ensure_gitignore()

        # Get the remote branch name
        remote_branch = await self.get_remote_branch()

        # Check if this is the first sync (no last_sync in config)
        config = self._load_config()
        is_first_sync = not config.get("last_sync")

        if is_first_sync:
            # First sync: reset to Overleaf content completely
            logger.info(f"First sync - resetting to Overleaf content (branch: {remote_branch})")
            await self._run_git("fetch", "origin", remote_branch, check=False, timeout=60)
            # Reset to origin/remote_branch, discarding local content
            result = await self._run_git("reset", "--hard", f"origin/{remote_branch}", check=False)
            if result.returncode != 0:
                return SyncResult(
                    success=False,
                    operation="pull",
                    message=f"Failed to sync with Overleaf: {result.stderr}",
                )
        else:
            # Regular sync: commit local changes and merge
            if filepath:
                # Only add the specific file
                await self._run_git("add", filepath, check=False)
                await self._run_git("commit", "-m", f"Auto-commit {filepath} before pull", check=False)
            else:
                # Add all changes
                await self._run_git("add", "-A", check=False)
                await self._run_git("commit", "-m", "Auto-commit before pull", check=False)

            # Pull from origin (fetch remote branch, merge into local branch)
            await self._run_git("fetch", "origin", remote_branch, check=False, timeout=60)
            result = await self._run_git("merge", f"origin/{remote_branch}", "--allow-unrelated-histories", check=False)

            # Check for conflicts
            if result.returncode != 0:
                if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                    # Get list of conflicted files
                    conflict_result = await self._run_git(
                        "diff", "--name-only", "--diff-filter=U", check=False
                    )
                    conflicts = [
                        f.strip() for f in conflict_result.stdout.split("\n") if f.strip()
                    ]

                    # Auto-resolve conflicts by keeping local version
                    logger.info(f"Auto-resolving {len(conflicts)} conflicts with local version")
                    for filepath in conflicts:
                        await self._run_git("checkout", "--ours", filepath, check=False)
                        await self._run_git("add", filepath, check=False)

                    # Complete the merge
                    await self._run_git("commit", "-m", "Auto-resolved conflicts (kept local)", check=False)

                    logger.info("Conflicts auto-resolved, continuing sync")
                else:
                    return SyncResult(
                        success=False,
                        operation="pull",
                        message=f"Pull failed: {result.stderr}",
                    )

        # Get list of changed files
        changed_files = []
        if "files changed" in result.stdout.lower():
            # Parse git output for changed files
            for line in result.stdout.split("\n"):
                if "|" in line:
                    # Format: "filename | N +++ ---"
                    changed_files.append(line.split("|")[0].strip())

        # Update last sync time
        config = self._load_config()
        config["last_sync"] = datetime.now().isoformat()
        self._save_config(config)

        return SyncResult(
            success=True,
            operation="pull",
            message=f"Successfully pulled from Overleaf. {len(changed_files)} files updated.",
            files_changed=changed_files,
        )

    async def push(self, commit_message: Optional[str] = None, filepath: Optional[str] = None) -> SyncResult:
        """
        Push local changes to Overleaf.

        Args:
            commit_message: Custom commit message (optional)
            filepath: Only commit this file (optional)

        Returns:
            SyncResult with push status
        """
        if not await self.is_git_repo():
            return SyncResult(
                success=False,
                operation="push",
                message="Not a git repository. Run setup first.",
            )

        remote_url = await self.get_remote_url()
        if not remote_url:
            return SyncResult(
                success=False,
                operation="push",
                message="No remote configured. Run setup first.",
            )

        # Ensure gitignore is set up and remove tracked files that should be ignored
        self._ensure_gitignore()
        await self._remove_ignored_from_cache()

        # Check for uncommitted changes (no need to fetch for this)
        status = await self.get_status(fetch=False)

        if filepath:
            # Only stage and commit the specific file
            await self._run_git("add", filepath, check=False)
            message = commit_message or f"Aura sync {filepath}: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            result = await self._run_git("commit", "-m", message, check=False)
            # Ignore commit failures due to nothing to commit
            combined_output = result.stdout + result.stderr
            if result.returncode != 0 and "nothing to commit" not in combined_output and "no changes added" not in combined_output:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"Commit failed for {filepath}: {error_msg}")
                return SyncResult(
                    success=False,
                    operation="push",
                    message=f"Commit failed: {error_msg}",
                )
        elif status.uncommitted_files:
            # Stage all changes
            await self._run_git("add", "-A", check=False)

            # Commit
            message = commit_message or f"Aura sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            result = await self._run_git("commit", "-m", message, check=False)
            # Ignore commit failures due to nothing to commit
            combined_output = result.stdout + result.stderr
            if result.returncode != 0 and "nothing to commit" not in combined_output and "no changes added" not in combined_output:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"Commit failed: {error_msg}")
                return SyncResult(
                    success=False,
                    operation="push",
                    message=f"Commit failed: {error_msg}",
                )

        # Push to origin (use local branch, push to remote branch)
        local_branch = status.branch or "master"
        remote_branch = await self.get_remote_branch()
        result = await self._run_git("push", "origin", f"{local_branch}:{remote_branch}", check=False)

        if result.returncode != 0:
            if "rejected" in result.stderr.lower():
                return SyncResult(
                    success=False,
                    operation="push",
                    message="Push rejected. Pull first to get remote changes.",
                )
            return SyncResult(
                success=False,
                operation="push",
                message=f"Push failed: {result.stderr}",
            )

        # Update last sync time
        config = self._load_config()
        config["last_sync"] = datetime.now().isoformat()
        self._save_config(config)

        return SyncResult(
            success=True,
            operation="push",
            message="Successfully pushed to Overleaf.",
            files_changed=status.uncommitted_files,
        )

    async def sync(self, commit_message: Optional[str] = None, filepath: Optional[str] = None) -> SyncResult:
        """
        Full sync: pull then push.

        This is the recommended sync operation as it handles
        both incoming and outgoing changes.

        Args:
            commit_message: Custom commit message for local changes
            filepath: Only sync this file if specified

        Returns:
            SyncResult with sync status
        """
        # First pull (with single file support)
        pull_result = await self.pull(filepath=filepath)
        if not pull_result.success:
            return pull_result

        # Then push (with single file support)
        push_result = await self.push(commit_message, filepath=filepath)
        if not push_result.success:
            return push_result

        return SyncResult(
            success=True,
            operation="sync",
            message="Successfully synced with Overleaf.",
            files_changed=pull_result.files_changed + push_result.files_changed,
        )

    async def resolve_conflict(self, filepath: str, keep: str = "ours") -> SyncResult:
        """
        Resolve a merge conflict by choosing a version.

        Args:
            filepath: Path to the conflicted file
            keep: "ours" (local) or "theirs" (remote)

        Returns:
            SyncResult
        """
        if keep == "ours":
            await self._run_git("checkout", "--ours", filepath, check=False)
        else:
            await self._run_git("checkout", "--theirs", filepath, check=False)

        await self._run_git("add", filepath, check=False)

        return SyncResult(
            success=True,
            operation="resolve",
            message=f"Resolved conflict in {filepath} using {keep} version.",
            files_changed=[filepath],
        )

    async def abort_merge(self) -> SyncResult:
        """Abort an in-progress merge."""
        result = await self._run_git("merge", "--abort", check=False)

        return SyncResult(
            success=result.returncode == 0,
            operation="abort",
            message="Merge aborted." if result.returncode == 0 else result.stderr,
        )
