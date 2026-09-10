#!/bin/bash
# Dashboard launcher script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting Affiliate Finder Dashboard..."

# Check if we're in the right place
if [ ! -f "$PROJECT_ROOT/src/config.py" ]; then
    echo "❌ Error: Run from affiliate-finder project root"
    exit 1
fi

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Kill existing processes on our ports
cleanup() {
    echo "🧹 Cleaning up..."
    pkill -f "uvicorn.*dashboard.backend" 2>/dev/null || true
    pkill -f "streamlit.*frontend" 2>/dev/null || true
    sleep 1
}

# Start backend
start_backend() {
    echo "🚀 Starting FastAPI backend on port 8000..."
    cd "$PROJECT_ROOT"
    python -m uvicorn dashboard.backend:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!
    echo "   Backend PID: $BACKEND_PID"
    
    # Wait for backend to be ready
    for i in {1..15}; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            echo "   ✅ Backend ready"
            return 0
        fi
        sleep 1
    done
    echo "   ❌ Backend failed to start"
    return 1
}

# Start frontend
start_frontend() {
    echo "🎨 Starting Streamlit frontend on port 8501..."
    cd "$PROJECT_ROOT/dashboard"
    DASHBOARD_API_URL=http://localhost:8000 python -m streamlit run frontend.py --server.port 8501 --server.headless true &
    FRONTEND_PID=$!
    echo "   Frontend PID: $FRONTEND_PID"
    
    # Wait for frontend to be ready
    for i in {1..20}; do
        if curl -s http://localhost:8501/_stcore/health >/dev/null 2>&1; then
            echo "   ✅ Frontend ready"
            return 0
        fi
        sleep 1
    done
    echo "   ❌ Frontend failed to start"
    return 1
}

# Main
main() {
    echo "╔══════════════════════════════════════════╗"
    echo "║   Affiliate Finder Dashboard Launcher    ║"
    echo "╚══════════════════════════════════════════╝"
    
    # Check dependencies
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 not found"
        exit 1
    fi
    
    # Trap cleanup on exit
    trap cleanup EXIT INT TERM
    
    cleanup
    
    # Start backend
    if ! start_backend; then
        echo "❌ Failed to start backend"
        exit 1
    fi
    
    # Start frontend
    if ! start_frontend; then
        echo "❌ Failed to start frontend"
        exit 1
    fi
    
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   ✅ Dashboard Running!                  ║"
    echo "╠══════════════════════════════════════════╣"
    echo "║  🎨 Frontend:  http://localhost:8501     ║"
    echo "║  🔧 Backend:   http://localhost:8000     ║"
    echo "║  📚 API Docs:  http://localhost:8000/docs║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "Press Ctrl+C to stop..."
    
    # Wait for user interrupt
    wait
}

main "$@"