# Local development helpers. See README "Local development".
API=services/api
WEB=apps/web
UV=cd $(API) && uv run

.PHONY: db migrate test lint seed-demo api worker web e2e demo stop contract

db:
	docker compose up -d --wait db

migrate: db
	$(UV) python manage.py migrate

test: db
	$(UV) pytest

lint:
	$(UV) ruff check .
	cd $(WEB) && npx tsc --noEmit

seed-demo: migrate
	$(UV) python manage.py seed_demo

api:
	$(UV) python manage.py runserver 127.0.0.1:8100

worker:
	$(UV) python manage.py run_worker

web:
	cd $(WEB) && npm run dev

e2e:
	cd tests/e2e && npx playwright test

demo:
	./scripts/demo.sh

stop:
	docker compose stop db

contract:
	$(UV) python manage.py spectacular --validate --fail-on-warn --file ../../contracts/openapi.yaml
	cd contracts && npm ci && npm run gen
