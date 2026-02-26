.PHONY: dev dev-backend dev-frontend build setup docker-up docker-down clean

dev:
	@echo "Starting Avni AI Platform..."
	@make dev-backend &
	@make dev-frontend

dev-backend:
	cd backend && ./venv/bin/python run.py

dev-frontend:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

setup:
	cd backend && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
	cd frontend && npm install

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

clean:
	rm -rf backend/__pycache__ backend/app/__pycache__
	rm -rf frontend/dist frontend/node_modules
