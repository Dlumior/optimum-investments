"""Punto de entrada reproducible:  python -m optimum <comando>

data      Excel (raw) -> interim -> processed
json      processed + config/caso.yaml -> data/json/input.json (validado)
run       input.json -> optimizador -> output.json  (a implementar en optimizer.py)
all       data + json + run
"""

from __future__ import annotations

import argparse
import sys

from optimum import paths


def cmd_data(_: argparse.Namespace) -> None:
    from optimum.cleaning import build_processed, save_processed
    from optimum.io.excel import export_interim

    paths.ensure_dirs()
    n1 = export_interim()
    n2 = save_processed(build_processed())
    print(f"interim: {len(n1)} hojas | processed: {len(n2)} tablas validadas")


def cmd_json(_: argparse.Namespace) -> None:
    from optimum.io.json_contract import build_input, validate_input, write_json

    doc = build_input()
    errors = validate_input(doc)
    if errors:
        sys.exit("input.json inválido:\n- " + "\n- ".join(errors))
    write_json(doc, paths.INPUT_JSON)
    print(
        f"{paths.INPUT_JSON.relative_to(paths.ROOT)} OK (caso {doc['caseId']}, "
        f"{len(doc['marketHistory'])} obs., {len(doc['instruments'])} instrumentos)"
    )


def cmd_run(args: argparse.Namespace) -> None:
    from optimum.io.json_contract import load_input, validate_output, write_json
    from optimum.optimizer import solve

    doc = load_input(args.input)
    try:
        out = solve(doc)
    except NotImplementedError as e:
        sys.exit(f"optimizer.solve aún no está implementado ({e}). Ver docs/formulacion.md.")
    errors = validate_output(out)
    if errors:
        sys.exit("output inválido:\n- " + "\n- ".join(errors))
    write_json(out, args.output)
    print(f"{args.output} -> status {out['status']}")
    if out["status"] == "OPTIMAL_INACCURATE":
        print("ADVERTENCIA: el solver reporta una solución inexacta; revisar constraintChecks.", file=sys.stderr)
    elif out["status"] != "OPTIMAL":
        sys.exit(f"El problema no tiene solución óptima (status {out['status']}); output.json sin posiciones.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="optimum")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("data").set_defaults(func=cmd_data)
    sub.add_parser("json").set_defaults(func=cmd_json)
    r = sub.add_parser("run")
    r.add_argument("--input", default=paths.INPUT_JSON, type=paths.Path)
    r.add_argument("--output", default=paths.OUTPUT_JSON, type=paths.Path)
    r.set_defaults(func=cmd_run)
    a = sub.add_parser("all")
    a.set_defaults(
        func=lambda ns: (cmd_data(ns), cmd_json(ns), cmd_run(ns)),
        input=paths.INPUT_JSON,
        output=paths.OUTPUT_JSON,
    )
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
