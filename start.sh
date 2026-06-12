#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Wohlig Pipeline Dashboard"
echo "=========================================="

# Check venv
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install/update backend deps
echo "Installing backend dependencies..."
pip install -q -r api/requirements.txt

# Check Node.js
if ! command -v node &> /dev/null; then
  echo "❌ Node.js is not installed. Please install Node.js (v18+) to run the dashboard."
  exit 1
fi

# Install frontend deps
echo "Installing frontend dependencies..."
cd dashboard
npm install
cd ..

# Start backend in background
echo "→ Starting FastAPI backend on http://127.0.0.1:8000"
python3 -c "
import sys
sys.path.insert(0, '.')
from api.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8000, reload=False)
" &
BACKEND_PID=$!

# Wait a moment for backend to bind
sleep 2

# Start frontend
echo "→ Starting Next.js dashboard on http://localhost:3000"
cd dashboard
exec npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Dashboard running at: http://localhost:3000"
echo "✅ API running at:        http://127.0.0.1:8000"
echo ""
echo "Press Ctrl+C to stop both."
wait
