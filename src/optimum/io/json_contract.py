"""Contrato JSON v1.0 (Anexo 1 del caso): construcción, validación y escritura.

Flujo:  data/processed/*.parquet + config/caso.yaml  ->  data/json/input.json
        optimizador(input.json)                     ->  data/json/output.json

El optimizador solo debe recibir el dict producido por `load_input()`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from optimum import paths
from optimum.cleaning import FACTORS, SEGMENTS, load_processed
from optimum.curves import NODE_YEARS, SEGMENT_BOUNDS

SCHEMA_VERSION = "1.0"
REQUIRED_INPUT_KEYS = [
    "schemaVersion",
    "caseId",
    "valuationDate",
    "horizonDate",
    "baseCurrency",
    "curveNodes",
    "curveSegments",
    "marketHistory",
    "instruments",
    "cashFlows",
    "calibrationSpreads",
    "factorMapping",
    "constraints",
    "transactionCosts",
    "fundingAlternatives",
    "caseParameters",
]
REQUIRED_OUTPUT_KEYS = [
    "schemaVersion",
    "caseId",
    "status",
    "objectiveValue",
    "valuation",
    "metrics",
    "riskModel",
    "positions",
    "weights",
    "constraintChecks",
]


# ----------------------------------------------------------------------- utilidades
def _clean(v: Any) -> Any:
    """Convierte tipos numpy/pandas a JSON puro; NaN -> None."""
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) else float(v)
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return _clean(df.reset_index().to_dict(orient="records"))


def _case_defaults(case_id: str) -> dict:
    """Parámetros de Case_Assumptions para el caso (se sobrescriben con caso.yaml)."""
    ca = load_processed("case_assumptions")
    rows = ca[ca["case"].isin([case_id])]
    out = {}
    for _, r in rows.iterrows():
        key = "".join(w.capitalize() if i else w.lower() for i, w in enumerate(r["parameter"].split()))
        val = r["value"]
        try:
            val = float(val)
        except ValueError:
            val = [x.strip() for x in val.split(";")] if ";" in val else val
        out[key] = val
    return out


# --------------------------------------------------------------------- construcción
def build_input(config_path: Path = paths.CASE_CONFIG) -> dict:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    case_id = cfg["caseId"]

    hist = load_processed("market_history")
    market = []
    for date, row in hist.iterrows():
        market.append(
            {
                "date": date,
                "spot": {c: {n: row[f"{c}_SPOT_{n}"] for n in NODE_YEARS} for c in ("PEN", "USD")},
                "forwardSwap": {c: {s: row[f"{c}_FWD_{s}"] for s in SEGMENTS} for c in ("PEN", "USD")},
                "fx": {"PENUSD": row["FX_PENUSD"]},
                "equityIndex": row["EQUITY_USD"],
            }
        )

    fmap = load_processed("factor_mapping")
    tree_t = load_processed("scenario_tree_d_transitions")
    tree_s = load_processed("scenario_tree_d_shocks")

    params = {**_case_defaults(case_id), **(cfg.get("caseParameters") or {})}
    params["seed"] = cfg.get("seed")

    doc = {
        "schemaVersion": cfg.get("schemaVersion", SCHEMA_VERSION),
        "caseId": case_id,
        "valuationDate": cfg["valuationDate"],
        "horizonDate": cfg["horizonDate"],
        "baseCurrency": cfg["baseCurrency"],
        "curveNodes": [{"id": k, "years": v} for k, v in NODE_YEARS.items()],
        "curveSegments": [{"id": s, "fromNode": a, "toNode": b} for s, (a, b) in SEGMENT_BOUNDS.items()],
        "marketHistory": market,
        "instruments": _records(load_processed("instruments")),
        "cashFlows": _records(load_processed("cash_flows")),
        "calibrationSpreads": load_processed("calibration_spreads")["calibration_spread"].to_dict(),
        "factorMapping": {"factorIds": list(fmap.columns), "rows": fmap.to_dict(orient="index")},
        "constraints": {
            "weights": _records(load_processed("constraints")),
            "common": cfg.get("commonConstraints", {}),
        },
        "transactionCosts": load_processed("transaction_costs")
        .drop(columns=["notes"])
        .to_dict(orient="index"),
        "fundingAlternatives": _records(load_processed("funding_alternatives")),
        "stressScenarios": _records(load_processed("stress_scenarios_c")),
        "scenarioTree": {"transitions": _records(tree_t), "shocks": _records(tree_s)},
        "caseParameters": params,
    }
    return _clean(doc)


# ----------------------------------------------------------------------- validación
def validate_input(doc: dict) -> list[str]:
    """Devuelve la lista de errores (vacía si el input es válido). Anexo 2, prompt 2."""
    errors: list[str] = []
    missing = [k for k in REQUIRED_INPUT_KEYS if k not in doc]
    if missing:
        return [f"Faltan claves: {missing}"]
    if doc["schemaVersion"] != SCHEMA_VERSION:
        errors.append(f"schemaVersion {doc['schemaVersion']} != {SCHEMA_VERSION}")
    if doc["caseId"] not in list("ABCDE"):
        errors.append(f"caseId inválido: {doc['caseId']}")

    node_ids = {n["id"] for n in doc["curveNodes"]}
    for seg in doc["curveSegments"]:
        if seg["fromNode"] not in node_ids or seg["toNode"] not in node_ids:
            errors.append(f"Segmento {seg['id']} referencia nodos inexistentes")
    seg_ids = {s["id"] for s in doc["curveSegments"]}

    dates = [m["date"] for m in doc["marketHistory"]]
    if len(dates) != len(set(dates)):
        errors.append("Observaciones históricas duplicadas en marketHistory")
    if dates != sorted(dates):
        errors.append("marketHistory no está ordenado por fecha")
    for m in doc["marketHistory"]:
        for ccy, segs in m["forwardSwap"].items():
            if set(segs) - seg_ids:
                errors.append(f"{m['date']}: segmentos inexistentes {set(segs) - seg_ids} ({ccy})")

    factor_ids = set(doc["factorMapping"]["factorIds"])
    if not factor_ids <= set(FACTORS):
        errors.append(f"factorIds desconocidos: {factor_ids - set(FACTORS)}")
    inst_ids = {i["id"] for i in doc["instruments"]}
    for inst in doc["instruments"] + doc["fundingAlternatives"]:
        ref = inst.get("reference_factor")
        if ref and ref not in factor_ids:
            errors.append(f"{inst['id']}: cupón flotante referencia factor no definido {ref}")
    for cf in doc["cashFlows"]:
        if cf["instrument_id"] not in inst_ids:
            errors.append(f"Flujo de instrumento inexistente {cf['instrument_id']}")
            break
    if set(doc["factorMapping"]["rows"]) != inst_ids:
        errors.append("factorMapping.rows no cubre exactamente los instrumentos")
    return errors


def validate_output(doc: dict) -> list[str]:
    missing = [k for k in REQUIRED_OUTPUT_KEYS if k not in doc]
    errors = [f"Faltan claves en output: {missing}"] if missing else []
    if doc.get("status") not in {"OPTIMAL", "OPTIMAL_INACCURATE", "INFEASIBLE", "UNBOUNDED", "ERROR"}:
        errors.append(f"status no reconocido: {doc.get('status')}")
    return errors


# -------------------------------------------------------------------------- I/O
def write_json(doc: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(doc), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_input(path: Path = paths.INPUT_JSON) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_input(doc)
    if errors:
        raise ValueError("input.json inválido:\n- " + "\n- ".join(errors))
    return doc
