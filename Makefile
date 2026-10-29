# Early Warning Credit Risk & EMI Stress Prediction - z/OS + ML
# `make install` once, then `make dev` and open http://localhost:3000

PY      := .venv/bin/python
UVICORN := .venv/bin/uvicorn

.PHONY: install dev api web tui login login-ssh test clean

install:            ## Python venv + dashboard packages
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r ml/requirements.txt
	cd dashboard && npm install --no-audit --no-fund

dev:                ## Start backend (:8000) and dashboard (:3000) together
	@echo "Backend  http://127.0.0.1:8000/docs"
	@echo "Dashboard http://localhost:3000"
	@trap 'kill 0' INT TERM EXIT; \
	$(UVICORN) api.main:app --host 127.0.0.1 --port 8000 & \
	cd dashboard && NEXT_TELEMETRY_DISABLED=1 npx next dev -p 3000

api:                ## Backend only
	$(UVICORN) api.main:app --host 127.0.0.1 --port 8000 --reload

web:                ## Dashboard only
	cd dashboard && NEXT_TELEMETRY_DISABLED=1 npx next dev -p 3000

tui:                ## Mainframe operator console (3270-style terminal UI)
	$(PY) -m tui

login:              ## Store z/OS host, user ID and password (password goes to the OS keyring)
	$(PY) -m pipeline.zosconf login

login-ssh:          ## Trust the z/OS SSH host key and install the EWS agent on USS
	$(PY) -m pipeline.uss trust
	$(PY) -m pipeline.uss install

test:               ## Unit tests (offline) + mainframe golden test if a batch run exists
	$(PY) -m pytest -q tests

clean:              ## Remove local run data (not the mainframe data sets)
	rm -rf data/runs data/ews.sqlite* dashboard/.next
