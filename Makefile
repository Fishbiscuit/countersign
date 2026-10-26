.PHONY: install console dev serve test acceptance lint typecheck bench verify docker

install:  ## Python environment + console dependencies
	uv sync
	cd console && npm ci --no-audit --no-fund

console:  ## Build the console into console/dist
	cd console && npx vite build

serve: console  ## Run Countersign (reads .env)
	uv run countersign serve

dev:  ## Console with hot reload against a running `make serve` on :8484
	cd console && npx vite

lint:
	uv run ruff check countersign bench demo tests
	uv run ruff format --check countersign bench demo tests

typecheck:
	cd console && npx tsc --noEmit

test:  ## Fast tests
	uv run pytest -q -m "not acceptance"

acceptance:  ## End-to-end through the real agent endpoint (starts the full stack)
	uv run pytest -q -m acceptance

bench:  ## Chaos bench: the same failures with and without Countersign
	uv run python -m bench.run

verify: lint typecheck test acceptance  ## Everything CI runs

docker:
	docker build -t countersign .
