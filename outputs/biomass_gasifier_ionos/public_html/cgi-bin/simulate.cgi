#!/usr/bin/env python3
"""CGI endpoint for running a biomass gasification simulation."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import traceback
from typing import Any

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, APP_DIR)

from feedstock import Feedstock  # noqa: E402
from gasifier import Gasifier, GasifierConditions  # noqa: E402
from tracker import record_request  # noqa: E402
from utils import flatten_dict  # noqa: E402


DEFAULT_INPUT = {
    "mass_flow_kg_h": 100.0,
    "mass_basis": "dry",
    "moisture_pct": 10.0,
    "C_pct": 50.0,
    "H_pct": 6.0,
    "O_pct": 42.0,
    "N_pct": 1.0,
    "S_pct": 0.1,
    "Cl_pct": 0.05,
    "ash_pct": 0.85,
    "cellulose_pct": 40.0,
    "hemicellulose_pct": 25.0,
    "lignin_pct": 25.0,
    "extractives_pct": 10.0,
    "plastics_pct": 0.0,
    "pe_pp_pct": 0.0,
    "ps_pct": 0.0,
    "pet_pct": 0.0,
    "pvc_pct": 0.0,
    "other_organics_pct": 0.0,
    "lhv_mj_kg": None,
    "hhv_mj_kg": None,
    "temperature_c": 850.0,
    "pressure_bar": 1.0,
    "residence_time_s": 2.0,
    "er": 0.30,
    "o2_flow_kmol_h": None,
    "agent": "air",
    "steam_biomass_ratio": 0.0,
    "model": "semi_empirical",
    "thermal_mode": "autothermal",
    "external_heat_input_kw": 0.0,
    "syngas_cooler_outlet_c": 40.0,
    "heat_exchanger_effectiveness": 0.75,
    "catalyst_type": "none",
    "catalyst_to_biomass_ratio": 0.0,
    "catalyst_activity": 1.0,
    "gasifier_type": "generic",
    "syngas_cooling_time_s": 2.0,
}


def optional_float(value: Any) -> float | None:
    """Convert empty CGI/JSON values to None."""
    if value in (None, ""):
        return None
    return float(value)


def result_to_csv(result: dict[str, Any]) -> str:
    """Serialize one result as a single CSV row."""
    flat = flatten_dict(result)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(flat))
    writer.writeheader()
    writer.writerow(flat)
    return output.getvalue()


def read_payload() -> dict[str, Any]:
    """Read JSON request body from CGI stdin."""
    length = int(os.environ.get("CONTENT_LENGTH") or "0")
    raw = sys.stdin.buffer.read(length).decode("utf-8") if length else "{}"
    return json.loads(raw or "{}")


def simulate_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Build model objects and run the simulation."""
    data = DEFAULT_INPUT | payload
    feedstock = Feedstock(
        mass_flow_kg_h=float(data["mass_flow_kg_h"]),
        mass_basis=str(data["mass_basis"]),
        moisture_pct=float(data["moisture_pct"]),
        C_pct=float(data["C_pct"]),
        H_pct=float(data["H_pct"]),
        O_pct=float(data["O_pct"]),
        N_pct=float(data["N_pct"]),
        S_pct=float(data["S_pct"]),
        Cl_pct=float(data["Cl_pct"]),
        ash_pct=float(data["ash_pct"]),
        cellulose_pct=float(data["cellulose_pct"]),
        hemicellulose_pct=float(data["hemicellulose_pct"]),
        lignin_pct=float(data["lignin_pct"]),
        extractives_pct=float(data["extractives_pct"]),
        plastics_pct=float(data["plastics_pct"]),
        pe_pp_pct=float(data["pe_pp_pct"]),
        ps_pct=float(data["ps_pct"]),
        pet_pct=float(data["pet_pct"]),
        pvc_pct=float(data["pvc_pct"]),
        other_organics_pct=float(data["other_organics_pct"]),
        lhv_mj_kg=optional_float(data["lhv_mj_kg"]),
        hhv_mj_kg=optional_float(data["hhv_mj_kg"]),
    )
    conditions = GasifierConditions(
        temperature_c=float(data["temperature_c"]),
        pressure_bar=float(data["pressure_bar"]),
        residence_time_s=float(data["residence_time_s"]),
        er=optional_float(data["er"]),
        o2_flow_kmol_h=optional_float(data["o2_flow_kmol_h"]),
        agent=str(data["agent"]),
        steam_biomass_ratio=float(data["steam_biomass_ratio"]),
        model=str(data["model"]),
        thermal_mode=str(data["thermal_mode"]),
        external_heat_input_kw=float(data["external_heat_input_kw"]),
        syngas_cooler_outlet_c=float(data["syngas_cooler_outlet_c"]),
        heat_exchanger_effectiveness=float(data["heat_exchanger_effectiveness"]),
        catalyst_type=str(data["catalyst_type"]),
        catalyst_to_biomass_ratio=float(data["catalyst_to_biomass_ratio"]),
        catalyst_activity=float(data["catalyst_activity"]),
        gasifier_type=str(data["gasifier_type"]),
        syngas_cooling_time_s=float(data["syngas_cooling_time_s"]),
    )
    return Gasifier(feedstock, conditions).simulate()


def respond(status: str, payload: dict[str, Any]) -> None:
    """Write a JSON CGI response."""
    body = json.dumps(payload, indent=2).encode("utf-8")
    headers = (
        f"Status: {status}\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "\r\n"
    ).encode("utf-8")
    sys.stdout.buffer.write(headers)
    sys.stdout.buffer.write(body)


def main() -> None:
    """CGI entry point."""
    status = "200 OK"
    try:
        result = simulate_from_payload(read_payload())
        payload = {"result": result, "csv": result_to_csv(result)}
    except Exception as exc:
        status = "400 Bad Request"
        payload = {
            "error": str(exc),
            "trace": traceback.format_exc(limit=4),
        }
    try:
        log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
        request_count = record_request(
            log_dir=log_dir,
            remote_ip=os.environ.get("REMOTE_ADDR", "unknown"),
            user_agent=os.environ.get("HTTP_USER_AGENT", ""),
            endpoint=os.environ.get("REQUEST_URI", "/cgi-bin/simulate.cgi"),
            status=status,
        )
        payload["tracking"] = {"request_count": request_count}
    except Exception as log_exc:
        payload["tracking"] = {"warning": f"Request log unavailable: {log_exc}"}
    respond(status, payload)


if __name__ == "__main__":
    main()
