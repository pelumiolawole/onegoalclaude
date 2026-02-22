#!/bin/bash
# infrastructure/scripts/setup.sh
# Run this once after cloning the repo to set up local development

set -e  # Exit on any error

echo "🎯 Setting up One Goal development environment..."

# ── Check prerequisites ────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required. Install from https://docker.com"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3.12+ is required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js 20+ is required"; exit 1; }

# ── Backend setup ──────────────────────────────────────────────────────
echo ""
echo "📦 Setting up Python backend..."

cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Copy env example
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env from .env.example"
    echo "   👉 Fill in your API keys in backend/.env before starting"
fi

cd ..

# ── Frontend setup ─────────────────────────────────────────────────────
echo ""
echo "📦 Setting up Next.js frontend..."

cd frontend
npm install

if [ ! -f .env.local ]; then
    cp .env.local.example .env.local 2>/dev/null || echo "⚠️  Create frontend/.env.local with your Supabase keys"
fi

cd ..

# ── Start infrastructure ───────────────────────────────────────────────
echo ""
echo "🐳 Starting PostgreSQL and Redis..."

cd infrastructure/docker
docker compose up -d postgres redis
cd ../..

# Wait for postgres to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 5

# ── Run migrations ─────────────────────────────────────────────────────
echo ""
echo "🗄️  Running database migrations..."

cd backend
source venv/bin/activate

# Run our raw SQL migrations (pgvector-specific setup)
for migration in db/migrations/*.sql; do
    echo "  Running $migration..."
    psql "postgresql://postgres:password@localhost:5432/onegoal" -f "$migration"
done

echo ""
echo "✅ One Goal is ready to run!"
echo ""
echo "Start the backend:"
echo "  cd backend && source venv/bin/activate && uvicorn main:app --reload"
echo ""
echo "Start the frontend (in a new terminal):"
echo "  cd frontend && npm run dev"
echo ""
echo "API docs available at: http://localhost:8000/docs"
echo "Frontend at:           http://localhost:3000"
