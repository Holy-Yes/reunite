# Common tasks. Run from the repo root with the venv active (or use .venv/bin/ prefixes).
PY ?= .venv/bin/python

.PHONY: test test-pg run seed seed-light eval eval-real migrate

test:            ## unit and API tests (SQLite, light models)
	cd backend && ../$(PY) -m pytest

test-pg:         ## the same suite on Postgres
	cd backend && TEST_DATABASE_URL=postgresql+psycopg://localhost/reunite_test ../$(PY) -m pytest

run:             ## the API on :8010
	cd backend && LC_ALL=en_US.UTF-8 ../$(PY) -m uvicorn app.main:app --port 8010 --reload

migrate:
	cd backend && ../$(PY) -m alembic -c alembic.ini upgrade head

seed:            ## wipe and reseed with the real models
	$(PY) scripts/seed_demo.py --reset

seed-light:      ## same, with tiny stand-in models (seconds)
	$(PY) scripts/seed_demo.py --reset --light

eval:            ## synthetic pairs (optimistic)
	$(PY) -m eval.synthetic_pairs && $(PY) -m eval.run_eval --pairs synthetic

eval-real:       ## your photographed pairs
	$(PY) -m eval.check_manifest && $(PY) -m eval.run_eval --pairs real
