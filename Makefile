# ==================== AI TRADING ECOSYSTEM MAKEFILE ====================
.PHONY: help setup dev prod test clean backup restore monitor logs

SHELL := /bin/bash
VERSION := $(shell git describe --tags --always --dirty)
COMMIT := $(shell git rev-parse --short HEAD)
BUILD_TIME := $(shell date -u '+%Y-%m-%d_%H:%M:%S')

# Colors
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

help: ## Show this help message
	@echo '$(BLUE)AI Trading Ecosystem Makefile$(NC)'
	@echo 'Usage: make [target]'
	@echo ''
	@echo '$(GREEN)Available targets:$(NC)'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# ==================== SETUP ====================
setup: ## Setup development environment
	@echo "$(GREEN)Setting up development environment...$(NC)"
	@make setup-backend
	@make setup-frontend
	@make setup-pre-commit
	@echo "$(GREEN)✓ Setup complete$(NC)"

setup-backend:
	@echo "Setting up backend..."
	@cd backend && python -m venv venv
	@cd backend && source venv/bin/activate && pip install -r requirements/dev.txt
	@cd backend && cp .env.example .env
	@echo "✓ Backend setup complete"

setup-frontend:
	@echo "Setting up frontend..."
	@cd frontend && npm install
	@cd frontend && cp .env.local.example .env.local
	@echo "✓ Frontend setup complete"

setup-pre-commit:
	@echo "Setting up pre-commit hooks..."
	@cd backend && source venv/bin/activate && pre-commit install
	@echo "✓ Pre-commit hooks installed"

# ==================== DEVELOPMENT ====================
dev: ## Start development environment
	@echo "$(GREEN)Starting development environment...$(NC)"
	@docker-compose up -d
	@make logs
	@echo "$(GREEN)✓ Development environment started$(NC)"

dev-build: ## Rebuild and start development environment
	@echo "$(GREEN)Rebuilding development environment...$(NC)"
	@docker-compose up -d --build
	@make logs

dev-down: ## Stop development environment
	@echo "$(YELLOW)Stopping development environment...$(NC)"
	@docker-compose down
	@echo "$(YELLOW)✓ Development environment stopped$(NC)"

dev-clean: ## Clean development environment (remove volumes)
	@echo "$(RED)Cleaning development environment...$(NC)"
	@docker-compose down -v
	@echo "$(RED)✓ Development environment cleaned$(NC)"

dev-logs: ## View development logs
	@docker-compose logs -f

dev-shell-backend: ## Open shell in backend container
	@docker-compose exec backend bash

dev-shell-frontend: ## Open shell in frontend container
	@docker-compose exec frontend sh

dev-shell-db: ## Open PostgreSQL shell
	@docker-compose exec postgres psql -U trading_user -d trading

# ==================== PRODUCTION ====================
prod: ## Start production environment
	@echo "$(GREEN)Starting production environment...$(NC)"
	@docker-compose -f docker-compose.prod.yml up -d
	@make prod-logs

prod-build: ## Rebuild and start production environment
	@echo "$(GREEN)Rebuilding production environment...$(NC)"
	@docker-compose -f docker-compose.prod.yml up -d --build

prod-down: ## Stop production environment
	@echo "$(YELLOW)Stopping production environment...$(NC)"
	@docker-compose -f docker-compose.prod.yml down

prod-logs: ## View production logs
	@docker-compose -f docker-compose.prod.yml logs -f

prod-scale: ## Scale services (usage: make prod-scale service=backend replicas=5)
	@docker-compose -f docker-compose.prod.yml up -d --scale $(service)=$(replicas)

# ==================== TESTING ====================
test: ## Run all tests
	@echo "$(GREEN)Running all tests...$(NC)"
	@make test-backend
	@make test-frontend
	@make test-integration
	@echo "$(GREEN)✓ All tests passed$(NC)"

test-backend: ## Run backend tests
	@echo "Running backend tests..."
	@cd backend && source venv/bin/activate && pytest tests/ -v --cov=. --cov-report=term-missing
	@echo "✓ Backend tests complete"

test-frontend: ## Run frontend tests
	@echo "Running frontend tests..."
	@cd frontend && npm run test
	@echo "✓ Frontend tests complete"

test-integration: ## Run integration tests
	@echo "Running integration tests..."
	@docker-compose up -d postgres redis mongodb
	@cd backend && source venv/bin/activate && pytest tests/integration/ -v
	@docker-compose down
	@echo "✓ Integration tests complete"

test-load: ## Run load tests
	@echo "Running load tests..."
	@locust -f tests/load/locustfile.py --host=http://localhost:8000
	@echo "✓ Load tests complete"

test-coverage: ## Generate test coverage report
	@echo "Generating coverage report..."
	@cd backend && source venv/bin/activate && pytest --cov=. --cov-report=html
	@open backend/htmlcov/index.html

# ==================== DATABASE ====================
db-migrate: ## Run database migrations
	@echo "Running database migrations..."
	@cd backend && source venv/bin/activate && alembic upgrade head
	@echo "✓ Migrations complete"

db-rollback: ## Rollback last migration
	@echo "Rolling back last migration..."
	@cd backend && source venv/bin/activate && alembic downgrade -1
	@echo "✓ Rollback complete"

db-revision: ## Create new migration revision
	@cd backend && source venv/bin/activate && alembic revision --autogenerate -m "$(message)"

db-seed: ## Seed database with test data
	@echo "Seeding database..."
	@cd backend && source venv/bin/activate && python scripts/seed_data.py
	@echo "✓ Database seeded"

db-backup: ## Backup database
	@echo "Backing up database..."
	@./scripts/backup.sh
	@echo "✓ Backup complete"

db-restore: ## Restore database from backup
	@echo "Restoring database from backup..."
	@./scripts/restore.sh $(file)
	@echo "✓ Restore complete"

# ==================== BUILD ====================
build: ## Build all services
	@echo "$(GREEN)Building all services...$(NC)"
	@make build-backend
	@make build-frontend
	@make build-services
	@echo "$(GREEN)✓ Build complete$(NC)"

build-backend:
	@echo "Building backend..."
	@cd backend && docker build -t trading-backend:$(VERSION) -f Dockerfile.prod .
	@docker tag trading-backend:$(VERSION) trading-backend:latest

build-frontend:
	@echo "Building frontend..."
	@cd frontend && docker build -t trading-frontend:$(VERSION) -f Dockerfile.prod .
	@docker tag trading-frontend:$(VERSION) trading-frontend:latest

build-services:
	@echo "Building services..."
	@cd services/market_data && docker build -t trading-market-data:$(VERSION) -f Dockerfile.prod .
	@cd services/trading_engine && docker build -t trading-trading-engine:$(VERSION) -f Dockerfile.prod .
	@cd services/ai_engine && docker build -t trading-ai-engine:$(VERSION) -f Dockerfile.prod .
	@cd services/notification && docker build -t trading-notification:$(VERSION) -f Dockerfile.prod .
	@cd services/websocket && docker build -t trading-websocket:$(VERSION) -f Dockerfile.prod .

build-push: ## Build and push images to registry
	@echo "Pushing images to registry..."
	@docker tag trading-backend:$(VERSION) $(REGISTRY)/trading-backend:$(VERSION)
	@docker tag trading-frontend:$(VERSION) $(REGISTRY)/trading-frontend:$(VERSION)
	@docker push $(REGISTRY)/trading-backend:$(VERSION)
	@docker push $(REGISTRY)/trading-frontend:$(VERSION)
	@echo "✓ Images pushed"

# ==================== DEPLOYMENT ====================
deploy: ## Deploy to environment (usage: make deploy env=staging)
	@echo "$(GREEN)Deploying to $(env)...$(NC)"
	@./scripts/deploy.sh $(env) $(VERSION)
	@echo "$(GREEN)✓ Deployment complete$(NC)"

deploy-rollback: ## Rollback deployment
	@echo "$(YELLOW)Rolling back deployment...$(NC)"
	@./scripts/rollback.sh $(env)
	@echo "$(YELLOW)✓ Rollback complete$(NC)"

deploy-status: ## Check deployment status
	@./scripts/status.sh $(env)

# ==================== KUBERNETES ====================
k8s-apply: ## Apply Kubernetes configurations
	@kubectl apply -f kubernetes/$(env)/

k8s-delete: ## Delete Kubernetes resources
	@kubectl delete -f kubernetes/$(env)/

k8s-logs: ## View Kubernetes logs
	@kubectl logs -f deployment/$(service) -n trading-$(env)

k8s-exec: ## Execute command in pod
	@kubectl exec -it deployment/$(service) -n trading-$(env) -- $(cmd)

k8s-scale: ## Scale deployment
	@kubectl scale deployment/$(service) --replicas=$(replicas) -n trading-$(env)

k8s-rollout: ## Check rollout status
	@kubectl rollout status deployment/$(service) -n trading-$(env)

k8s-dashboard: ## Open Kubernetes dashboard
	@kubectl proxy &
	@open http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/

# ==================== MONITORING ====================
monitor: ## Open monitoring dashboards
	@echo "$(GREEN)Opening monitoring dashboards...$(NC)"
	@open http://localhost:9090  # Prometheus
	@open http://localhost:3001  # Grafana
	@open http://localhost:5601  # Kibana
	@open http://localhost:5555  # Flower
	@echo "$(GREEN)✓ Monitoring dashboards opened$(NC)"

monitor-grafana: ## Open Grafana
	@open http://localhost:3001

monitor-prometheus: ## Open Prometheus
	@open http://localhost:9090

monitor-kibana: ## Open Kibana
	@open http://localhost:5601

monitor-flower: ## Open Flower (Celery monitoring)
	@open http://localhost:5555

# ==================== LOGS ====================
logs: ## View all logs
	@docker-compose logs -f

logs-backend: ## View backend logs
	@docker-compose logs -f backend

logs-frontend: ## View frontend logs
	@docker-compose logs -f frontend

logs-worker: ## View worker logs
	@docker-compose logs -f backend-worker

logs-db: ## View database logs
	@docker-compose logs -f postgres

# ==================== CLEANUP ====================
clean: ## Clean all temporary files
	@echo "$(RED)Cleaning temporary files...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.pyd" -delete
	@find . -type f -name ".coverage" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type d -name "*.egg" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@find . -type d -name "htmlcov" -exec rm -rf {} +
	@echo "$(RED)✓ Clean complete$(NC)"

clean-docker: ## Clean Docker resources
	@echo "$(RED)Cleaning Docker resources...$(NC)"
	@docker system prune -f
	@docker volume prune -f
	@docker network prune -f
	@echo "$(RED)✓ Docker clean complete$(NC)"

clean-all: clean clean-docker ## Clean everything
	@echo "$(RED)Cleaning everything...$(NC)"
	@rm -rf backend/venv
	@rm -rf frontend/node_modules
	@rm -rf frontend/.next
	@rm -rf data/
	@echo "$(RED)✓ Complete clean$(NC)"

# ==================== UTILITIES ====================
version: ## Show version information
	@echo "Version: $(VERSION)"
	@echo "Commit: $(COMMIT)"
	@echo "Build Time: $(BUILD_TIME)"

env: ## Show environment variables
	@echo "$(BLUE)Environment Variables:$(NC)"
	@env | grep -E '^(APP|DB|REDIS|JWT|BINANCE|OPENAI)'

lint: ## Run linters
	@echo "Running linters..."
	@cd backend && source venv/bin/activate && flake8 .
	@cd backend && source venv/bin/activate && black --check .
	@cd backend && source venv/bin/activate && isort --check-only .
	@cd frontend && npm run lint
	@echo "✓ Linting complete"

format: ## Format code
	@echo "Formatting code..."
	@cd backend && source venv/bin/activate && black .
	@cd backend && source venv/bin/activate && isort .
	@cd frontend && npm run format
	@echo "✓ Formatting complete"

security: ## Run security checks
	@echo "Running security checks..."
	@cd backend && source venv/bin/activate && bandit -r .
	@cd backend && source venv/bin/activate && safety check
	@cd frontend && npm audit
	@echo "✓ Security checks complete"

docs: ## Generate documentation
	@echo "Generating documentation..."
	@cd docs && mkdocs build
	@echo "✓ Documentation generated"

help: ## Show this help message
	@echo '$(BLUE)AI Trading Ecosystem Makefile$(NC)'
	@echo 'Usage: make [target]'
	@echo ''
	@echo '$(GREEN)Available targets:$(NC)'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

.DEFAULT_GOAL := help