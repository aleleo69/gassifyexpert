"""Shared constants and utility functions for the biomass gasifier tool."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import csv
import json
from pathlib import Path
from typing import Any


ATOMIC_WEIGHTS = {
    "C": 12.011,
    "H": 1.008,
    "O": 15.999,
    "N": 14.007,
    "S": 32.06,
    "Cl": 35.45,
}

MOLECULAR_WEIGHTS = {
    "CO": 28.010,
    "CO2": 44.009,
    "H2": 2.016,
    "CH4": 16.043,
    "C2H4": 28.054,
    "C2H6": 30.070,
    "H2O": 18.015,
    "N2": 28.014,
    "O2": 31.998,
    "H2S": 34.076,
    "SO2": 64.058,
    "HCl": 36.458,
    "Cl2": 70.900,
    "NH3": 17.031,
    "HCN": 27.026,
    "NO": 30.006,
    "NO2": 46.005,
    "N2O": 44.013,
}

SPECIES_ATOMS = {
    "CO": {"C": 1, "O": 1},
    "CO2": {"C": 1, "O": 2},
    "H2": {"H": 2},
    "CH4": {"C": 1, "H": 4},
    "C2H4": {"C": 2, "H": 4},
    "C2H6": {"C": 2, "H": 6},
    "H2O": {"H": 2, "O": 1},
    "N2": {"N": 2},
    "O2": {"O": 2},
    "H2S": {"H": 2, "S": 1},
    "SO2": {"S": 1, "O": 2},
    "HCl": {"H": 1, "Cl": 1},
    "Cl2": {"Cl": 2},
    "NH3": {"N": 1, "H": 3},
    "HCN": {"H": 1, "C": 1, "N": 1},
    "NO": {"N": 1, "O": 1},
    "NO2": {"N": 1, "O": 2},
    "N2O": {"N": 2, "O": 1},
}

LHV_MJ_PER_NM3 = {
    "H2": 10.8,
    "CO": 12.63,
    "CH4": 35.8,
    "C2H4": 59.0,
    "C2H6": 63.8,
}

NM3_PER_KMOL = 22.414
AIR_N2_O2_MOLAR_RATIO = 3.76


def clamp(value: float, lower: float, upper: float) -> float:
    """Limit *value* to the inclusive interval [lower, upper]."""
    return max(lower, min(upper, value))


def percent_to_fraction(value: float) -> float:
    """Convert a percent value to a 0-1 fraction."""
    return value / 100.0


def normalize(values: dict[str, float]) -> dict[str, float]:
    """Return a normalized copy of a positive-valued dictionary."""
    total = sum(max(v, 0.0) for v in values.values())
    if total <= 0:
        return {k: 0.0 for k in values}
    return {k: max(v, 0.0) / total for k, v in values.items()}


def dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses to serializable dictionaries."""
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [dataclass_to_dict(v) for v in obj]
    return obj


def write_json(data: dict[str, Any], path: str | Path) -> None:
    """Write a simulation result to JSON."""
    Path(path).write_text(json.dumps(dataclass_to_dict(data), indent=2), encoding="utf-8")


def flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dictionaries for simple CSV output."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_dict(value, name))
        elif isinstance(value, list):
            flat[name] = "; ".join(map(str, value))
        else:
            flat[name] = value
    return flat


def write_csv(data: dict[str, Any], path: str | Path) -> None:
    """Write a single simulation result as one CSV row."""
    flat = flatten_dict(dataclass_to_dict(data))
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat))
        writer.writeheader()
        writer.writerow(flat)
