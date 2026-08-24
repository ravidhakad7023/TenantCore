.PHONY: test run run-prod migrate check

test:
	pytest -v --cov=app --cov-report=term-missing

run:
	docker-compose up --build

run-prod:
	docker-compose -f docker-compose.prod.yml up --build -d

migrate:
	alembic upgrade head

check:
	docker-compose ps
