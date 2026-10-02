# Uso: make <objetivo>.  Todo es reproducible desde cero con:  make setup all
PY      ?= .venv/bin/python
CASE    ?= $(shell grep -E '^caseId:' config/caso.yaml | sed -E 's/.*"(.)".*/\1/')
ZIP     := entrega/OP01_Caso$(CASE)_$(shell date +%Y%m%d).zip
ZIP_FULL := entrega/OP01_Caso$(CASE)_completo_$(shell date +%Y%m%d).zip
NB_SRC  := notebooks/entrega/OP01_optimum_investments.ipynb
NB_BUILD := entrega/build

.PHONY: help setup data json run sensitivity all test lint fmt notebooks notebook-entrega report report-clean \
	entrega entrega-completa clean

help:          ## Lista los objetivos
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n", $$1, $$2}'

setup:         ## Crea .venv (uv), instala el paquete en modo editable y configura nbstripout
	uv venv
	uv pip install -e ".[dev]"
	$(PY) -m ipykernel install --user --name optimum --display-name "Python (optimum)"
	-.venv/bin/nbstripout --install

data:          ## Excel raw -> data/interim -> data/processed (validado)
	$(PY) -m optimum data

json:          ## processed + config/caso.yaml -> data/json/input.json
	$(PY) -m optimum json

run:           ## input.json -> optimizador -> output.json
	$(PY) -m optimum run

sensitivity:   ## input.json -> sensibilidades S1-S9 -> data/json/sensitivity.json (5-8 min)
	$(PY) -m optimum sensitivity

all: data json run   ## Pipeline completo

test:          ## Pruebas automáticas
	$(PY) -m pytest -q

lint:          ## Revisión estática
	.venv/bin/ruff check src tests notebooks

fmt:           ## Formateo
	.venv/bin/ruff format src tests && .venv/bin/ruff check --fix src tests

notebooks:     ## Ejecuta todos los notebooks en orden (verifica reproducibilidad)
	for nb in notebooks/[0-9]*.ipynb; do \
	  $(PY) -m jupyter nbconvert --to notebook --execute --inplace "$$nb" || exit 1; done

report:        ## Compila informe_latex/main.tex con LuaLaTeX local (latexmk)
	cd informe_latex && latexmk -lualatex -interaction=nonstopmode -halt-on-error -output-directory=out main.tex

report-clean:  ## Limpia auxiliares de LaTeX
	rm -rf informe_latex/out/*

notebook-entrega: ## Regenera el notebook autocontenido desde src y lo ejecuta junto a input.json (D-25)
	$(PY) scripts/build_notebook_entrega.py
	rm -rf $(NB_BUILD) && mkdir -p $(NB_BUILD)
	cp $(NB_SRC) data/json/input.json $(NB_BUILD)/
	cd $(NB_BUILD) && $(abspath $(PY)) -m jupyter nbconvert --to notebook --execute --inplace \
	  --ExecutePreprocessor.timeout=1800 $(notdir $(NB_SRC))
	$(PY) -c "import json, sys; a, b = (json.load(open(f)) for f in sys.argv[1:]); \
	  [d['solver'].pop('time', None) for d in (a, b)]; \
	  sys.exit(0 if a == b else 'output.json del notebook difiere de data/json/output.json')" \
	  $(NB_BUILD)/output.json data/json/output.json
	@echo "-> $(NB_BUILD)/$(notdir $(NB_SRC)) ejecutado; output.json coincide con data/json/output.json"

entrega:       ## ZIP de entrega: informe PDF, input.json, output.json y notebook ejecutado
	@test -f informe_latex/out/main.pdf || (echo "Falta compilar el informe: make report" && exit 1)
	@test -f $(NB_BUILD)/output.json || (echo "Falta ejecutar el notebook: make notebook-entrega" && exit 1)
	rm -f $(ZIP)
	zip -j $(ZIP) informe_latex/out/main.pdf data/json/input.json data/json/output.json \
	  $(NB_BUILD)/$(notdir $(NB_SRC))
	@echo "-> $(ZIP)"

entrega-completa: ## ZIP con todo el proyecto (código, pruebas, datos, docs e informe)
	@test -f informe_latex/out/main.pdf || (echo "Falta compilar el informe: make report" && exit 1)
	@test -f data/json/output.json || (echo "Falta output.json: make run" && exit 1)
	rm -f $(ZIP_FULL)
	zip -r $(ZIP_FULL) README.md pyproject.toml Makefile config src tests notebooks scripts \
	  data/json/input.json data/json/output.json data/raw \
	  docs/ia docs/decisiones.md docs/formulacion.md \
	  -x '*__pycache__*' '*.ipynb_checkpoints*'
	zip -j $(ZIP_FULL) informe_latex/out/main.pdf
	@echo "-> $(ZIP_FULL)"

clean:         ## Borra datos derivados (interim/processed/json) y cachés
	find data/interim data/processed data/json -type f ! -name .gitkeep -delete
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
