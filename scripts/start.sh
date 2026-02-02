#!/bin/bash
#
# YouResearch Development Startup Script
#
# Starts both backend and frontend for development.
# Usage: ./scripts/start.sh [--backend-only | --frontend-only | --test | --landing]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8001
FRONTEND_PORT=3001
BACKEND_DIR="$(dirname "$0")/../backend"
FRONTEND_DIR="$(dirname "$0")/../app"
SANDBOX_DIR="$(dirname "$0")/../sandbox"
BACKEND_PID=""
FRONTEND_PID=""
USE_UV=false
HAS_TECTONIC=false
HAS_LOCAL_TEX=false
HAS_DOCKER=false

# Resolve absolute paths
BACKEND_DIR="$(cd "$BACKEND_DIR" && pwd)"
FRONTEND_DIR="$(cd "$FRONTEND_DIR" && pwd)"
SANDBOX_DIR="$(cd "$SANDBOX_DIR" && pwd)"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    log_info "Cleaning up..."

    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        log_info "Stopping backend (PID: $BACKEND_PID)"
        kill "$BACKEND_PID" 2>/dev/null || true
    fi

    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        log_info "Stopping frontend (PID: $FRONTEND_PID)"
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi

    # Kill any orphaned processes
    pkill -f "uvicorn main:app --port $BACKEND_PORT" 2>/dev/null || true

    log_info "Cleanup complete"
}

# Set up trap for cleanup
trap cleanup EXIT INT TERM

wait_for_backend() {
    local max_attempts=30
    local attempt=1

    log_info "Waiting for backend to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
            log_success "Backend is ready!"
            return 0
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    log_error "Backend failed to start after $max_attempts seconds"
    return 1
}

wait_for_frontend() {
    local max_attempts=60
    local attempt=1

    log_info "Waiting for frontend to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://127.0.0.1:$FRONTEND_PORT" > /dev/null 2>&1; then
            log_success "Frontend is ready!"
            return 0
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    log_error "Frontend failed to start after $max_attempts seconds"
    return 1
}

install_with_brew() {
    local package=$1
    if command -v brew &> /dev/null; then
        log_info "Installing $package via Homebrew..."
        brew install "$package"
        return $?
    else
        return 1
    fi
}

# =============================================================================
# LaTeX Environment Detection
# =============================================================================

check_tectonic() {
    # Check for bundled Tectonic
    local tectonic_path="$BACKEND_DIR/bin/tectonic"
    if [ -x "$tectonic_path" ]; then
        HAS_TECTONIC=true
        return 0
    fi

    # Check PATH
    if command -v tectonic &> /dev/null; then
        HAS_TECTONIC=true
        return 0
    fi

    return 1
}

check_local_tex() {
    # Check common pdflatex locations
    if command -v pdflatex &> /dev/null; then
        HAS_LOCAL_TEX=true
        return 0
    fi

    # Check MacTeX default locations
    local tex_paths=(
        "/Library/TeX/texbin/pdflatex"
        "/usr/local/texlive/2026/bin/universal-darwin/pdflatex"
        "/usr/local/texlive/2025/bin/universal-darwin/pdflatex"
        "/usr/local/texlive/2024/bin/universal-darwin/pdflatex"
        "/usr/local/texlive/2023/bin/universal-darwin/pdflatex"
    )

    for tex_path in "${tex_paths[@]}"; do
        if [ -x "$tex_path" ]; then
            HAS_LOCAL_TEX=true
            return 0
        fi
    done

    return 1
}

check_docker() {
    if command -v docker &> /dev/null; then
        # Check if Docker daemon is running
        if docker info &> /dev/null; then
            HAS_DOCKER=true
            return 0
        fi
    fi
    return 1
}

check_latex_environment() {
    log_info "Checking LaTeX compilation environment..."

    check_tectonic || true
    check_local_tex || true
    check_docker || true

    if [ "$HAS_TECTONIC" = true ]; then
        local tectonic_version=$("$BACKEND_DIR/bin/tectonic" --version 2>/dev/null | head -1 || echo "Tectonic")
        log_success "Tectonic found: $tectonic_version (bundled)"
        log_info "  LaTeX compilation ready out-of-the-box"
    elif [ "$HAS_LOCAL_TEX" = true ]; then
        local tex_version=$(pdflatex --version 2>/dev/null | head -1 || echo "Unknown version")
        log_success "Local TeX found: $tex_version"
        log_info "  LaTeX compilation will use local installation (fast)"
    elif [ "$HAS_DOCKER" = true ]; then
        log_success "Docker found and running"
        log_info "  LaTeX compilation will use Docker (isolated)"

        # Check if texlive image exists
        if docker images texlive/texlive --format "{{.Repository}}" | grep -q "texlive"; then
            log_success "Docker TeX image is ready"
        else
            log_warn "Docker TeX image not found"
            log_info "  Image will be pulled automatically on first compile"
        fi
    else
        log_error "No LaTeX compiler available!"
        log_info "  Tectonic binary missing from backend/bin/"
        log_info "  Re-download or reinstall OpenResearch"
    fi
}

build_docker_image() {
    log_info "Building Docker LaTeX image..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        log_info "Download from: https://docker.com/products/docker-desktop"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        log_info "Start Docker Desktop and try again"
        exit 1
    fi

    log_info "Pulling Docker LaTeX image..."
    if docker pull texlive/texlive:latest-small; then
        log_success "Docker TeX image pulled successfully!"
    else
        log_error "Failed to pull Docker image"
        exit 1
    fi
}

check_dependencies() {
    log_info "Checking dependencies..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 is not installed"
        log_info "Install with: brew install python3"
        exit 1
    fi
    log_success "Python3 found: $(python3 --version)"

    # Check for uv (preferred) or pip (fallback)
    if command -v uv &> /dev/null; then
        log_success "uv found: $(uv --version)"
        USE_UV=true
    else
        log_warn "uv not found, falling back to pip"
        log_info "  To install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh"
        USE_UV=false
    fi

    # Check Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js is not installed"
        if install_with_brew node; then
            log_success "Node.js installed via Homebrew"
        else
            log_info "Install manually:"
            log_info "  - Homebrew: brew install node"
            log_info "  - Or download from: https://nodejs.org/"
            exit 1
        fi
    fi
    log_success "Node.js found: $(node --version)"

    # Check npm
    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed (usually comes with Node.js)"
        log_info "Reinstall Node.js to get npm"
        exit 1
    fi
    log_success "npm found: $(npm --version)"

    # Check if backend dependencies are installed
    if [ "$USE_UV" = true ]; then
        # Check if uv.lock exists and sync if needed
        if [ -f "$BACKEND_DIR/uv.lock" ]; then
            log_info "Syncing backend dependencies with uv..."
            (cd "$BACKEND_DIR" && uv sync --quiet)
        fi
    else
        # Check for multiple key dependencies to ensure requirements are up to date
        if ! python3 -c "import fastapi; import bs4; import scholarly" 2>/dev/null; then
            log_warn "Missing dependencies. Installing backend dependencies..."
            pip3 install -r "$BACKEND_DIR/requirements.txt"
        fi
    fi

    # Check if frontend dependencies are installed
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_warn "Node modules not installed. Installing frontend dependencies..."
        (cd "$FRONTEND_DIR" && npm install)
    fi

    log_success "All core dependencies satisfied"

    # Check LaTeX environment
    echo ""
    check_latex_environment
}

# =============================================================================
# Start Functions
# =============================================================================

start_backend() {
    log_info "Starting backend on port $BACKEND_PORT..."

    # Check if port is already in use
    if lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warn "Port $BACKEND_PORT is already in use"
        log_info "Killing existing process..."
        lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    cd "$BACKEND_DIR"

    if [ "$USE_UV" = true ]; then
        uv run uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT --reload &
    else
        python3 -m uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT --reload &
    fi
    BACKEND_PID=$!

    if ! wait_for_backend; then
        log_error "Failed to start backend"
        exit 1
    fi

    log_success "Backend started (PID: $BACKEND_PID)"
}

start_frontend() {
    log_info "Starting frontend on port $FRONTEND_PORT..."

    # Check if port is already in use
    if lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warn "Port $FRONTEND_PORT is already in use"
        log_info "Killing existing process..."
        lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    cd "$FRONTEND_DIR"
    npm run next:dev &
    FRONTEND_PID=$!

    if ! wait_for_frontend; then
        log_error "Failed to start frontend"
        exit 1
    fi

    log_success "Frontend started (PID: $FRONTEND_PID)"
}

start_electron() {
    log_info "Starting Electron desktop app..."
    log_info "(This will also start the Next.js server)"

    # Check if port is already in use
    if lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warn "Port $FRONTEND_PORT is already in use"
        log_info "Killing existing process..."
        lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    cd "$FRONTEND_DIR"

    # npm run dev starts both Next.js and Electron with concurrently
    npm run dev &
    FRONTEND_PID=$!

    # Wait for Next.js to be ready (Electron waits automatically via wait-on)
    if ! wait_for_frontend; then
        log_error "Failed to start frontend"
        exit 1
    fi

    log_success "Electron app launched"
}

# =============================================================================
# Test Functions
# =============================================================================

run_tests() {
    log_info "Running API tests..."

    local tests_passed=0
    local tests_failed=0

    # Test 1: Health check
    log_info "Test 1: Health check..."
    response=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/health")
    if echo "$response" | grep -q '"status":"ok"'; then
        log_success "Health check passed"
        tests_passed=$((tests_passed + 1))
    else
        log_error "Health check failed: $response"
        tests_failed=$((tests_failed + 1))
    fi

    # Test 2: List projects
    log_info "Test 2: List projects..."
    response=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/projects")
    if echo "$response" | grep -qE '^\['; then
        log_success "List projects passed"
        tests_passed=$((tests_passed + 1))
    else
        log_error "List projects failed: $response"
        tests_failed=$((tests_failed + 1))
    fi

    # Test 3: List tools
    log_info "Test 3: List agent tools..."
    response=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/tools")
    if echo "$response" | grep -qE '^\['; then
        log_success "List tools passed"
        tests_passed=$((tests_passed + 1))
    else
        log_error "List tools failed: $response"
        tests_failed=$((tests_failed + 1))
    fi

    # Test 4: List subagents
    log_info "Test 4: List subagents..."
    response=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/subagents")
    if echo "$response" | grep -qE '^\['; then
        log_success "List subagents passed"
        tests_passed=$((tests_passed + 1))
    else
        log_error "List subagents failed: $response"
        tests_failed=$((tests_failed + 1))
    fi

    # Test 5: Create test project
    log_info "Test 5: Create test project..."
    response=$(curl -s -X POST "http://127.0.0.1:$BACKEND_PORT/api/projects" \
        -H "Content-Type: application/json" \
        -d '{"name": "test-project-'$(date +%s)'", "template": "article"}')
    if echo "$response" | grep -q '"name"'; then
        log_success "Create project passed"
        tests_passed=$((tests_passed + 1))

        # Extract project name for further tests
        PROJECT_NAME=$(echo "$response" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)

        # Test 6: Get project files
        log_info "Test 6: Get project files..."
        response=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/projects/$PROJECT_NAME/files")
        if echo "$response" | grep -qE '^\['; then
            log_success "Get project files passed"
            tests_passed=$((tests_passed + 1))
        else
            log_error "Get project files failed: $response"
            tests_failed=$((tests_failed + 1))
        fi

        # Test 7: Read file
        log_info "Test 7: Read file..."
        response=$(curl -s -X POST "http://127.0.0.1:$BACKEND_PORT/api/files/read" \
            -H "Content-Type: application/json" \
            -d "{\"project_path\": \"$HOME/youresearch-projects/$PROJECT_NAME\", \"filename\": \"main.tex\"}")
        if echo "$response" | grep -q '"content"'; then
            log_success "Read file passed"
            tests_passed=$((tests_passed + 1))
        else
            log_error "Read file failed: $response"
            tests_failed=$((tests_failed + 1))
        fi

        # Test 8: Write file
        log_info "Test 8: Write file..."
        response=$(curl -s -X POST "http://127.0.0.1:$BACKEND_PORT/api/files/write" \
            -H "Content-Type: application/json" \
            -d "{\"project_path\": \"$HOME/youresearch-projects/$PROJECT_NAME\", \"filename\": \"test.txt\", \"content\": \"Hello from test!\"}")
        if echo "$response" | grep -q '"success":true'; then
            log_success "Write file passed"
            tests_passed=$((tests_passed + 1))
        else
            log_error "Write file failed: $response"
            tests_failed=$((tests_failed + 1))
        fi

    else
        log_error "Create project failed: $response"
        tests_failed=$((tests_failed + 1))
    fi

    # Summary
    echo ""
    log_info "========================================="
    log_info "Test Summary"
    log_info "========================================="
    log_success "Passed: $tests_passed"
    if [ $tests_failed -gt 0 ]; then
        log_error "Failed: $tests_failed"
    else
        log_info "Failed: $tests_failed"
    fi
    echo ""

    if [ $tests_failed -gt 0 ]; then
        return 1
    fi
    return 0
}

# =============================================================================
# Main
# =============================================================================

print_banner() {
    echo ""
    echo -e "${BLUE}  ╔═══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}  ║                                       ║${NC}"
    echo -e "${BLUE}  ║   ${GREEN}Y O U W R I T E${BLUE}   Dev Server      ║${NC}"
    echo -e "${BLUE}  ║                                       ║${NC}"
    echo -e "${BLUE}  ║   Local-first LaTeX IDE with AI       ║${NC}"
    echo -e "${BLUE}  ║                                       ║${NC}"
    echo -e "${BLUE}  ╚═══════════════════════════════════════╝${NC}"
    echo ""
}

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --backend-only    Start only the backend server"
    echo "  --frontend-only   Start only the frontend server (web)"
    echo "  --electron        Start full Electron desktop app"
    echo "  --landing         Open landing page in browser after starting"
    echo "  --test            Run API tests after starting backend"
    echo "  --test-only       Run API tests only (assumes backend is running)"
    echo "  --build-docker    Build the Docker LaTeX image"
    echo "  --check-env       Check environment and exit (no servers started)"
    echo "  --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Start backend + web frontend"
    echo "  $0 --landing          # Start and open landing page"
    echo "  $0 --electron         # Start backend + Electron desktop app"
    echo "  $0 --backend-only     # Start only backend (for testing)"
    echo "  $0 --check-env        # Check all dependencies including LaTeX"
    echo "  $0 --build-docker     # Build Docker image for LaTeX compilation"
    echo ""
    echo "LaTeX Compilation:"
    echo "  YouResearch supports multiple LaTeX compilation methods:"
    echo "    1. Tectonic (bundled) - fastest, no setup required"
    echo "    2. Local TeX (MacTeX/TeX Live) - fast, no Docker required"
    echo "    3. Docker - isolated, reproducible"
    echo ""
    echo "  If none available, Tectonic will be downloaded automatically."
    echo ""
}

main() {
    print_banner

    local backend_only=false
    local frontend_only=false
    local run_test=false
    local test_only=false
    local use_electron=false
    local build_docker=false
    local check_env_only=false
    local open_landing=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backend-only)
                backend_only=true
                shift
                ;;
            --frontend-only)
                frontend_only=true
                shift
                ;;
            --electron)
                use_electron=true
                shift
                ;;
            --landing)
                open_landing=true
                shift
                ;;
            --test)
                run_test=true
                shift
                ;;
            --test-only)
                test_only=true
                shift
                ;;
            --build-docker)
                build_docker=true
                shift
                ;;
            --check-env)
                check_env_only=true
                shift
                ;;
            --help)
                print_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                print_usage
                exit 1
                ;;
        esac
    done

    # Build Docker image mode
    if [ "$build_docker" = true ]; then
        build_docker_image
        exit 0
    fi

    # Test only mode
    if [ "$test_only" = true ]; then
        run_tests
        exit $?
    fi

    # Check dependencies
    check_dependencies

    # Check env only mode
    if [ "$check_env_only" = true ]; then
        echo ""
        log_success "Environment check complete!"
        exit 0
    fi

    # Start services
    if [ "$frontend_only" = false ]; then
        start_backend
    fi

    # Run tests if requested
    if [ "$run_test" = true ]; then
        run_tests
    fi

    if [ "$backend_only" = false ]; then
        if [ "$use_electron" = true ]; then
            start_electron
        else
            start_frontend
        fi
    fi

    # Print status
    echo ""
    log_info "========================================="
    log_info "Services Running"
    log_info "========================================="
    if [ "$frontend_only" = false ]; then
        log_success "Backend:  http://127.0.0.1:$BACKEND_PORT"
        log_info "  API Docs: http://127.0.0.1:$BACKEND_PORT/docs"
    fi
    if [ "$backend_only" = false ]; then
        if [ "$use_electron" = true ]; then
            log_success "Electron: Desktop app launched"
        else
            log_success "Frontend: http://127.0.0.1:$FRONTEND_PORT"
            log_info "  Landing: http://127.0.0.1:$FRONTEND_PORT/YouResearch"
        fi
    fi

    # Open landing page if requested
    if [ "$open_landing" = true ] && [ "$backend_only" = false ] && [ "$use_electron" = false ]; then
        log_info "Opening landing page in browser..."
        sleep 1
        open "http://127.0.0.1:$FRONTEND_PORT/YouResearch"
    fi

    # Show LaTeX status
    echo ""
    if [ "$HAS_TECTONIC" = true ]; then
        log_info "LaTeX: Tectonic (bundled)"
    elif [ "$HAS_LOCAL_TEX" = true ]; then
        log_info "LaTeX: Local TeX installation"
    elif [ "$HAS_DOCKER" = true ]; then
        log_info "LaTeX: Docker (texlive/texlive)"
    else
        log_warn "LaTeX: Not available"
    fi

    echo ""
    log_info "Press Ctrl+C to stop all services"
    echo ""

    # Wait for processes
    wait
}

main "$@"
