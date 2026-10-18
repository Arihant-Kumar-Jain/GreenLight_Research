.PHONY: setup dev serve build check test eval

setup: ## Install backend (uv, incl. the local reranker extra) and frontend (npm) dependencies
	cd backend && uv sync --extra local
	cd web && npm install

dev: ## API on :8100 (auto-reload) + Vite UI on :5180. Ctrl-C stops both.
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && uv run uvicorn glr.api:app --reload --port 8100 --reload-dir glr) & \
	(cd web && npm run dev) & \
	wait

build: ## Production build of the UI into web/dist (served by the backend)
	cd web && npm run build

serve: build ## One server on :8100 with the built UI
	cd backend && uv run uvicorn glr.api:app --port 8100

eval: ## Retrieval eval + gate calibration on a finished project: make eval P=<project_id>
	cd backend && uv run python scripts/eval_retrieval.py $(P)

test: ## Offline tests (scripted model; no keys, no network)
	cd backend && uv run pytest -q

check: ## Type-check + build the UI, lint, import-check and test the backend
	cd web && npx tsc -b && npx vite build && npx oxlint src
	cd backend && uv run python -c "import glr.api; print('backend ok')" && uv run pytest -q
