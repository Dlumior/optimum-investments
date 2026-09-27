# Uso: make <objetivo>.  Todo es reproducible desde cero con:  make setup all
PY      ?= .venv/bin/python
CASE    ?= $(shell grep -E '^caseId:' config/caso.yaml | sed -E 's/.*"(.)".*/\1/')
ZIP     := entrega/OP01_Caso$(CASE)_$(shell date +%Y%m%d).zip

.PHONY: help setup data json run all test lint fmt notebooks report report-clean entrega clean

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

entrega:       ## Construye el ZIP de entrega (código, input/output JSON, informe, anexos)
	@test -f informe_latex/out/main.pdf || (echo "Falta compilar el informe: make report" && exit 1)
	@test -f data/json/output.json || (echo "Falta output.json: make run" && exit 1)
	rm -f $(ZIP)
	zip -r $(ZIP) README.md pyproject.toml Makefile config src tests notebooks \
	  data/json/input.json data/json/output.json data/raw \
	  docs/ia docs/decisiones.md docs/formulacion.md \
	  -x '*__pycache__*' '*.ipynb_checkpoints*'
	zip -j $(ZIP) informe_latex/out/main.pdf
	@echo "-> $(ZIP)"

clean:         ## Borra datos derivados (interim/processed/json) y cachés
	find data/interim data/processed data/json -type f ! -name .gitkeep -delete
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
