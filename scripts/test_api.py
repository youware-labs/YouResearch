#!/usr/bin/env python3
"""
Aura Backend API Test Suite

Comprehensive tests for all backend endpoints.
Usage: python scripts/test_api.py [--verbose] [--base-url URL]
"""

import asyncio
import argparse
import sys
import json
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class TestConfig:
    base_url: str = "http://127.0.0.1:8001"
    verbose: bool = False
    test_project_name: str = ""


# =============================================================================
# Test Results
# =============================================================================

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    duration_ms: float = 0


class TestSuite:
    def __init__(self, config: TestConfig):
        self.config = config
        self.results: list[TestResult] = []
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        # Disable proxy for local connections (trust_env=False is key)
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=30.0,
            proxy=None,
            trust_env=False,  # Don't read proxy from environment
        )
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    def log(self, message: str):
        if self.config.verbose:
            print(f"  {message}")

    def add_result(self, result: TestResult):
        self.results.append(result)
        status = "✓" if result.passed else "✗"
        color = "\033[92m" if result.passed else "\033[91m"
        reset = "\033[0m"
        print(f"{color}{status}{reset} {result.name} ({result.duration_ms:.0f}ms)")
        if not result.passed and result.message:
            print(f"  Error: {result.message}")

    # =========================================================================
    # Health & Info Tests
    # =========================================================================

    async def test_health(self):
        """Test /api/health endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/health")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self.add_result(TestResult("Health Check", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Health Check", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Health Check", False, str(e)))

    async def test_root(self):
        """Test / endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if data.get("service") == "Aura Backend":
                    self.add_result(TestResult("Root Endpoint", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Root Endpoint", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Root Endpoint", False, str(e)))

    async def test_list_tools(self):
        """Test /api/tools endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/tools")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"Found {len(data)} tools")
                    self.add_result(TestResult("List Tools", True, duration_ms=duration))
                    return
            self.add_result(TestResult("List Tools", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("List Tools", False, str(e)))

    async def test_list_subagents(self):
        """Test /api/subagents endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/subagents")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"Found {len(data)} subagents: {[s.get('name') for s in data]}")
                    self.add_result(TestResult("List Subagents", True, duration_ms=duration))
                    return
            self.add_result(TestResult("List Subagents", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("List Subagents", False, str(e)))

    # =========================================================================
    # Project Tests
    # =========================================================================

    async def test_list_projects(self):
        """Test /api/projects GET endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/projects")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"Found {len(data)} projects")
                    self.add_result(TestResult("List Projects", True, duration_ms=duration))
                    return
            self.add_result(TestResult("List Projects", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("List Projects", False, str(e)))

    async def test_create_project(self):
        """Test /api/projects POST endpoint"""
        import time
        start = time.time()

        # Generate unique project name
        import uuid
        self.config.test_project_name = f"test-{uuid.uuid4().hex[:8]}"

        try:
            response = await self.client.post(
                "/api/projects",
                json={"name": self.config.test_project_name, "template": "article"}
            )
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if data.get("name") == self.config.test_project_name:
                    self.log(f"Created project: {self.config.test_project_name}")
                    self.add_result(TestResult("Create Project", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Create Project", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Create Project", False, str(e)))

    async def test_get_project_files(self):
        """Test /api/projects/{name}/files endpoint"""
        import time
        start = time.time()

        if not self.config.test_project_name:
            self.add_result(TestResult("Get Project Files", False, "No test project created"))
            return

        try:
            response = await self.client.get(f"/api/projects/{self.config.test_project_name}/files")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"Found {len(data)} files: {[f.get('name') for f in data]}")
                    self.add_result(TestResult("Get Project Files", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Get Project Files", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Get Project Files", False, str(e)))

    # =========================================================================
    # File Operations Tests
    # =========================================================================

    async def test_read_file(self):
        """Test /api/files/read endpoint"""
        import time
        start = time.time()

        if not self.config.test_project_name:
            self.add_result(TestResult("Read File", False, "No test project created"))
            return

        project_path = Path.home() / "aura-projects" / self.config.test_project_name

        try:
            response = await self.client.post(
                "/api/files/read",
                json={"project_path": str(project_path), "filename": "main.tex"}
            )
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if "content" in data:
                    content_preview = data["content"][:50].replace("\n", "\\n")
                    self.log(f"Content preview: {content_preview}...")
                    self.add_result(TestResult("Read File", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Read File", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Read File", False, str(e)))

    async def test_write_file(self):
        """Test /api/files/write endpoint"""
        import time
        start = time.time()

        if not self.config.test_project_name:
            self.add_result(TestResult("Write File", False, "No test project created"))
            return

        project_path = Path.home() / "aura-projects" / self.config.test_project_name
        test_content = f"% Test file created at {time.time()}\n% This is a test.\n"

        try:
            response = await self.client.post(
                "/api/files/write",
                json={
                    "project_path": str(project_path),
                    "filename": "test-output.tex",
                    "content": test_content
                }
            )
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.log(f"Wrote test file: test-output.tex")
                    self.add_result(TestResult("Write File", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Write File", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Write File", False, str(e)))

    async def test_read_nonexistent_file(self):
        """Test /api/files/read with nonexistent file"""
        import time
        start = time.time()

        if not self.config.test_project_name:
            self.add_result(TestResult("Read Nonexistent File (404)", False, "No test project created"))
            return

        project_path = Path.home() / "aura-projects" / self.config.test_project_name

        try:
            response = await self.client.post(
                "/api/files/read",
                json={"project_path": str(project_path), "filename": "nonexistent-file.tex"}
            )
            duration = (time.time() - start) * 1000

            if response.status_code == 404:
                self.add_result(TestResult("Read Nonexistent File (404)", True, duration_ms=duration))
                return
            self.add_result(TestResult("Read Nonexistent File (404)", False, f"Expected 404, got {response.status_code}", duration))
        except Exception as e:
            self.add_result(TestResult("Read Nonexistent File (404)", False, str(e)))

    # =========================================================================
    # HITL Tests
    # =========================================================================

    async def test_hitl_pending(self):
        """Test /api/hitl/pending endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/hitl/pending")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"Found {len(data)} pending approvals")
                    self.add_result(TestResult("HITL Pending", True, duration_ms=duration))
                    return
            self.add_result(TestResult("HITL Pending", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("HITL Pending", False, str(e)))

    async def test_hitl_config(self):
        """Test /api/hitl/config endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/hitl/config")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if "approval_required" in data:
                    self.log(f"Approval required for: {data.get('approval_required', [])}")
                    self.add_result(TestResult("HITL Config", True, duration_ms=duration))
                    return
            self.add_result(TestResult("HITL Config", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("HITL Config", False, str(e)))

    # =========================================================================
    # Steering Tests
    # =========================================================================

    async def test_steering_pending(self):
        """Test /api/steering/pending endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/steering/pending")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if "count" in data:
                    self.log(f"Pending steering messages: {data.get('count', 0)}")
                    self.add_result(TestResult("Steering Pending", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Steering Pending", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Steering Pending", False, str(e)))

    async def test_steering_config(self):
        """Test /api/steering/config endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/steering/config")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if "max_queue_size" in data:
                    self.add_result(TestResult("Steering Config", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Steering Config", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Steering Config", False, str(e)))

    # =========================================================================
    # Planning Tests
    # =========================================================================

    async def test_planning_current(self):
        """Test /api/planning/current endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/planning/current")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                # Should return has_plan: false if no plan exists
                if "has_plan" in data:
                    self.log(f"Has plan: {data.get('has_plan')}")
                    self.add_result(TestResult("Planning Current", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Planning Current", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Planning Current", False, str(e)))

    async def test_planning_history(self):
        """Test /api/planning/history endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.get("/api/planning/history")
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if "count" in data:
                    self.log(f"Plan history count: {data.get('count', 0)}")
                    self.add_result(TestResult("Planning History", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Planning History", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Planning History", False, str(e)))

    # =========================================================================
    # Compression Tests
    # =========================================================================

    async def test_compression_stats(self):
        """Test /api/compression/stats endpoint"""
        import time
        start = time.time()
        try:
            response = await self.client.post(
                "/api/compression/stats",
                json={"history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ]}
            )
            duration = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if "estimated_tokens" in data:
                    self.log(f"Estimated tokens: {data.get('estimated_tokens')}")
                    self.add_result(TestResult("Compression Stats", True, duration_ms=duration))
                    return
            self.add_result(TestResult("Compression Stats", False, f"Unexpected response: {response.text}", duration))
        except Exception as e:
            self.add_result(TestResult("Compression Stats", False, str(e)))

    # =========================================================================
    # Run All Tests
    # =========================================================================

    async def run_all(self):
        """Run all tests"""
        print("\n" + "=" * 60)
        print("  Aura Backend API Test Suite")
        print("=" * 60)
        print(f"  Base URL: {self.config.base_url}")
        print("=" * 60 + "\n")

        # Health & Info
        print("Health & Info:")
        await self.test_health()
        await self.test_root()
        await self.test_list_tools()
        await self.test_list_subagents()

        # Projects
        print("\nProjects:")
        await self.test_list_projects()
        await self.test_create_project()
        await self.test_get_project_files()

        # File Operations
        print("\nFile Operations:")
        await self.test_read_file()
        await self.test_write_file()
        await self.test_read_nonexistent_file()

        # HITL
        print("\nHuman-in-the-Loop:")
        await self.test_hitl_pending()
        await self.test_hitl_config()

        # Steering
        print("\nSteering:")
        await self.test_steering_pending()
        await self.test_steering_config()

        # Planning
        print("\nPlanning:")
        await self.test_planning_current()
        await self.test_planning_history()

        # Compression
        print("\nCompression:")
        await self.test_compression_stats()

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print("\n" + "=" * 60)
        print(f"  Results: {passed}/{total} passed")
        if failed > 0:
            print(f"  \033[91m{failed} tests failed\033[0m")
        else:
            print("  \033[92mAll tests passed!\033[0m")
        print("=" * 60 + "\n")

        # Cleanup info
        if self.config.test_project_name:
            project_path = Path.home() / "aura-projects" / self.config.test_project_name
            print(f"Note: Test project created at: {project_path}")
            print("      You may delete it manually if not needed.\n")

        return failed == 0


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Aura Backend API Test Suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Backend base URL")
    args = parser.parse_args()

    config = TestConfig(
        base_url=args.base_url,
        verbose=args.verbose,
    )

    # Check if backend is running
    try:
        async with httpx.AsyncClient(timeout=5.0, proxy=None, trust_env=False) as client:
            response = await client.get(f"{config.base_url}/api/health")
            if response.status_code != 200:
                print(f"Error: Backend not responding at {config.base_url}")
                print("Please start the backend first: ./scripts/start.sh --backend-only")
                sys.exit(1)
    except Exception as e:
        print(f"Error: Cannot connect to backend at {config.base_url}")
        print(f"       {e}")
        print("\nPlease start the backend first:")
        print("  cd backend && uvicorn main:app --port 8001")
        sys.exit(1)

    async with TestSuite(config) as suite:
        success = await suite.run_all()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
