# Local development helpers. See README "Local development".
API=services/api
WEB=apps/web
# Local commands run as SALLIMHA_ENV=local unless the caller sets it (settings refuse an unset value).
UV=cd $(API) && SALLIMHA_ENV=$${SALLIMHA_ENV:-local} uv run

.PHONY: db migrate test lint seed-demo api worker web e2e demo demo-clean demo-code stop contract

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

demo-clean:
	SEED_ARGS= ./scripts/demo.sh

# Current second-factor code for a synthetic demo account (manager, admin or owner). Local/test only.
WHO ?= manager
demo-code:
	$(UV) python manage.py demo_totp $(WHO)

stop:
	docker compose stop db

contract:
	$(UV) python manage.py spectacular --validate --fail-on-warn --file ../../contracts/openapi.yaml
	cd contracts && npm ci && npm run gen
