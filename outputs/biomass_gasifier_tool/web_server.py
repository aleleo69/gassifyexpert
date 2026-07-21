"""Small standard-library web UI for the biomass gasifier simulator."""

from __future__ import annotations

import argparse
import csv
import io
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from feedstock import Feedstock
from gasifier import Gasifier, GasifierConditions
from tracker import record_request
from utils import flatten_dict


LOCAL_LOG_DIR = str(Path(__file__).resolve().parent / "logs")


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
    "reduction_zone_severity": 0.75,
}

LAST_RESULT: dict[str, Any] | None = None
LAST_CSV = ""


def _optional_float(value: Any) -> float | None:
    """Convert blank JSON/form values to None and numbers to float."""
    if value in (None, ""):
        return None
    return float(value)


def simulate_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a web payload and run the gasifier."""
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
        lhv_mj_kg=_optional_float(data["lhv_mj_kg"]),
        hhv_mj_kg=_optional_float(data["hhv_mj_kg"]),
    )
    conditions = GasifierConditions(
        temperature_c=float(data["temperature_c"]),
        pressure_bar=float(data["pressure_bar"]),
        residence_time_s=float(data["residence_time_s"]),
        er=_optional_float(data["er"]),
        o2_flow_kmol_h=_optional_float(data["o2_flow_kmol_h"]),
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
        reduction_zone_severity=float(data["reduction_zone_severity"]),
    )
    return Gasifier(feedstock, conditions).simulate()


def result_to_csv(result: dict[str, Any]) -> str:
    """Serialize one result as CSV."""
    flat = flatten_dict(result)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(flat))
    writer.writeheader()
    writer.writerow(flat)
    return output.getvalue()


HTML = r"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Biomass Gasifier</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --line: #d8dee6;
      --text: #1f2933;
      --muted: #667085;
      --accent: #166534;
      --accent-2: #0f766e;
      --danger: #b42318;
      --warn: #b54708;
      --ok: #027a48;
      --code: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }
    header {
      min-height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 18px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 5;
    }
    h1 {
      font-size: 18px;
      line-height: 1.2;
      margin: 0;
      font-weight: 700;
    }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
      gap: 12px;
      padding: 12px;
      max-width: 1500px;
      margin: 0 auto;
    }
    section, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .inputs {
      align-self: start;
      position: sticky;
      top: 68px;
      max-height: calc(100vh - 80px);
      overflow: auto;
    }
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      font-weight: 700;
      color: #344054;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
    }
    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    input, select {
      width: 100%;
      height: 34px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 6px 8px;
      font: inherit;
      color: var(--text);
      background: #fff;
    }
    input:focus, select:focus {
      outline: 2px solid rgba(15, 118, 110, 0.18);
      border-color: var(--accent-2);
    }
    .sum-check {
      margin: 0 12px 12px;
      padding: 8px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      color: var(--muted);
      background: #f8fafc;
      font-size: 12px;
      font-weight: 700;
    }
    .sum-check.ok { color: #166534; border-color: #86efac; background: #f0fdf4; }
    .sum-check.err { color: #b42318; border-color: #fca5a5; background: #fef2f2; }
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      padding: 12px;
      border-top: 1px solid var(--line);
    }
    button, .button {
      height: 34px;
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #111827;
      border-radius: 6px;
      padding: 0 12px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
    }
    button.primary {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .segmented {
      display: inline-flex;
      gap: 2px;
      padding: 2px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      background: #f8fafc;
    }
    .segmented button {
      height: 26px;
      border: 0;
      border-radius: 4px;
      padding: 0 9px;
      background: transparent;
      color: #475467;
      font-size: 12px;
    }
    .segmented button.active {
      background: #ffffff;
      color: #0f766e;
      box-shadow: 0 1px 2px rgba(16, 24, 40, .12);
    }
    button:disabled, .button.disabled {
      opacity: .55;
      cursor: wait;
      pointer-events: none;
    }
    .results {
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .kpis {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .kpi {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 78px;
    }
    .kpi small {
      display: block;
      color: var(--muted);
      font-weight: 700;
      margin-bottom: 8px;
    }
    .kpi strong {
      font-size: 21px;
      line-height: 1.1;
      color: #111827;
    }
    .tables {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-variant-numeric: tabular-nums;
    }
    th, td {
      padding: 7px 9px;
      border-bottom: 1px solid #edf0f4;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child { text-align: left; }
    th {
      color: #475467;
      background: #f8fafc;
      font-size: 12px;
    }
    .panel-body { padding: 10px 12px; overflow: auto; }
    .status {
      font-weight: 800;
      color: var(--muted);
    }
    .status.ok { color: var(--ok); }
    .status.err { color: var(--danger); }
    .warnings {
      margin: 0;
      padding-left: 18px;
      color: var(--warn);
    }
    pre {
      margin: 0;
      padding: 12px;
      overflow: auto;
      max-height: 420px;
      color: var(--code);
      background: #f8fafc;
      border-radius: 6px;
      border: 1px solid #edf0f4;
      font-size: 12px;
    }
    .downloads {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; }
      .inputs { position: static; max-height: none; }
      .kpis, .tables { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      header { align-items: flex-start; flex-direction: column; }
      .grid { grid-template-columns: 1fr; }
      .downloads { width: 100%; }
      button, .button { flex: 1 1 auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Biomass Gasifier</h1>
    <div class="downloads">
      <span id="status" class="status">Ready</span>
      <a id="downloadJson" class="button disabled" download="gasifier_result.json" href="#">JSON</a>
      <a id="downloadCsv" class="button disabled" download="gasifier_result.csv" href="#">CSV</a>
    </div>
  </header>
  <main>
    <section class="inputs">
      <form id="simForm">
        <div class="section-title">Feedstock</div>
        <div class="grid">
          <label>Massa [kg/h]<input name="mass_flow_kg_h" type="number" step="any" value="100"></label>
          <label>Base massa<select name="mass_basis"><option value="dry">dry</option><option value="wet">wet</option></select></label>
          <label>Umidita [%]<input name="moisture_pct" type="number" step="any" value="10"></label>
          <label>Inerti/ceneri [% secco]<input name="ash_pct" type="number" step="any" value="0.85"></label>
          <label>C [%]<input name="C_pct" type="number" step="any" value="50"></label>
          <label>H [%]<input name="H_pct" type="number" step="any" value="6"></label>
          <label>O [%]<input name="O_pct" type="number" step="any" value="42"></label>
          <label>N [%]<input name="N_pct" type="number" step="any" value="1"></label>
          <label>S [%]<input name="S_pct" type="number" step="any" value="0.1"></label>
          <label>Cl [%]<input name="Cl_pct" type="number" step="any" value="0.05"></label>
          <label>PCI [MJ/kg]<input name="lhv_mj_kg" type="number" step="any" placeholder="opzionale"></label>
          <label>PCS [MJ/kg]<input name="hhv_mj_kg" type="number" step="any" placeholder="opzionale"></label>
        </div>
        <div id="elementalSum" class="sum-check"></div>
        <div class="section-title">Strutturali</div>
        <div class="grid">
          <label>Cellulosa [%]<input name="cellulose_pct" type="number" step="any" value="40"></label>
          <label>Emicellulosa [%]<input name="hemicellulose_pct" type="number" step="any" value="25"></label>
          <label>Lignina [%]<input name="lignin_pct" type="number" step="any" value="25"></label>
          <label>Estrattivi [%]<input name="extractives_pct" type="number" step="any" value="10"></label>
          <label>Plastiche totali [%]<input name="plastics_pct" type="number" min="0" step="any" value="0"></label>
          <label>PE/PP [%]<input name="pe_pp_pct" type="number" min="0" step="any" value="0"></label>
          <label>PS [%]<input name="ps_pct" type="number" min="0" step="any" value="0"></label>
          <label>PET [%]<input name="pet_pct" type="number" min="0" step="any" value="0"></label>
          <label>PVC [%]<input name="pvc_pct" type="number" min="0" step="any" value="0"></label>
          <label>Altri organici [%]<input name="other_organics_pct" type="number" min="0" step="any" value="0"></label>
        </div>
        <div id="structuralSum" class="sum-check"></div>
        <div class="section-title">Gasificatore</div>
        <div class="grid">
          <label>Temperatura [C]<input name="temperature_c" type="number" step="any" value="850"></label>
          <label>Pressione [bar]<input name="pressure_bar" type="number" step="any" value="1"></label>
          <label>Residenza [s]<input name="residence_time_s" type="number" step="any" value="2"></label>
          <label>ER<input name="er" type="number" step="any" value="0.30"></label>
          <label>O2 [kmol/h]<input name="o2_flow_kmol_h" type="number" step="any" placeholder="opzionale"></label>
          <label>Agente<select name="agent"><option>air</option><option>oxygen</option><option>steam</option><option>air+steam</option></select></label>
          <label>Steam/biomass<input name="steam_biomass_ratio" type="number" step="any" value="0"></label>
          <label>Modello<select name="model"><option>semi_empirical</option><option>stoichiometric_equilibrium</option><option>hybrid</option></select></label>
          <label>Tipo gassificatore<select name="gasifier_type"><option value="generic">generico</option><option value="updraft">updraft</option><option value="downdraft">downdraft</option><option value="bubbling_fluidized_bed">letto fluido bollente</option><option value="circulating_fluidized_bed">letto fluido circolante</option><option value="entrained_flow">entrained-flow</option></select></label>
          <label>Regime termico<select name="thermal_mode"><option value="autothermal">autotermico</option><option value="allothermal">allotermico</option></select></label>
          <label>Potenza termica esterna [kW]<input name="external_heat_input_kw" type="number" min="0" step="any" value="0"></label>
          <label>Syngas dopo recupero [C]<input name="syngas_cooler_outlet_c" type="number" min="0" step="any" value="40"></label>
          <label>Tempo raffreddamento syngas [s]<input name="syngas_cooling_time_s" type="number" min="0.01" step="any" value="2"></label>
          <label>Severità zona riducente [0-1]<input name="reduction_zone_severity" type="number" min="0" max="1" step="0.05" value="0.75"></label>
          <label>Efficienza scambiatore [0-1]<input name="heat_exchanger_effectiveness" type="number" min="0" max="1" step="0.01" value="0.75"></label>
          <label>Catalizzatore<select name="catalyst_type"><option value="none">nessuno</option><option value="olivine">olivina</option><option value="calcined_olivine">olivina calcinata</option><option value="limestone">calcare</option><option value="dolomite">dolomite</option><option value="nickel_based">base nichel</option></select></label>
          <label>Catalizzatore/biomassa [kg/kg]<input name="catalyst_to_biomass_ratio" type="number" min="0" step="0.01" value="0"></label>
          <label>Attività relativa [0-1]<input name="catalyst_activity" type="number" min="0" max="1" step="0.05" value="1"></label>
        </div>
        <div class="actions">
          <button class="primary" type="submit">Simula</button>
          <button id="resetExample" type="button">Esempio</button>
        </div>
      </form>
    </section>
    <div class="results">
      <div class="kpis">
        <div class="kpi"><small>Gas secco</small><strong id="dryFlow">-</strong></div>
        <div class="kpi"><small>PCI syngas</small><strong id="lhv">-</strong></div>
        <div class="kpi"><small>Char</small><strong id="charYield">-</strong></div>
        <div class="kpi"><small>CGE / Overall</small><strong id="cge">-</strong></div>
      </div>
      <section>
        <div class="section-title">
          <span id="gasTableTitle">Gas secco</span>
          <span class="segmented" aria-label="Base gas">
            <button id="gasDryToggle" class="active" type="button">Secco</button>
            <button id="gasWetToggle" type="button">Umido</button>
          </span>
        </div>
        <div class="panel-body"><table id="gasTable"></table></div>
      </section>
      <div class="tables">
        <section>
          <div class="section-title">Rese e portate</div>
          <div class="panel-body"><table id="yieldTable"></table></div>
        </section>
        <section>
          <div class="section-title">Bilanci</div>
          <div class="panel-body"><table id="balanceTable"></table></div>
        </section>
      </div>
      <div class="tables">
        <section>
          <div class="section-title">Trace pollutants</div>
          <div class="panel-body"><table id="traceTable"></table></div>
        </section>
        <section>
          <div class="section-title">Char [% massa]</div>
          <div class="panel-body"><table id="charTable"></table></div>
        </section>
      </div>
      <section>
        <div class="section-title">PCS feed e aria</div>
        <div class="panel-body"><table id="energyAirTable"></table></div>
      </section>
      <section>
        <div class="section-title">Effetto catalizzatore</div>
        <div class="panel-body"><table id="catalystTable"></table></div>
      </section>
      <section>
        <div class="section-title">Profilo gassificatore</div>
        <div class="panel-body"><table id="reactorTable"></table></div>
      </section>
      <section>
        <div class="section-title">Warning e incertezze</div>
        <div class="panel-body"><ul id="warnings" class="warnings"></ul></div>
      </section>
      <section>
        <div class="section-title">Output JSON</div>
        <div class="panel-body"><pre id="jsonOut">{}</pre></div>
      </section>
    </div>
  </main>
  <script>
    const form = document.getElementById('simForm');
    const statusEl = document.getElementById('status');
    const downloadJson = document.getElementById('downloadJson');
    const downloadCsv = document.getElementById('downloadCsv');
    let latestResult = null;
    let latestCsv = '';
    let jsonUrl = '';
    let csvUrl = '';
    let gasBasis = 'dry';

    function val(name) {
      const el = form.elements[name];
      return el.value === '' ? null : (el.type === 'number' ? Number(el.value) : el.value);
    }

    const elementalFields = ['C_pct', 'H_pct', 'O_pct', 'N_pct', 'S_pct', 'Cl_pct', 'ash_pct'];
    const structuralFields = [
      'cellulose_pct', 'hemicellulose_pct', 'lignin_pct',
      'extractives_pct', 'plastics_pct', 'other_organics_pct'
    ];
    const compositionTolerance = 0.5;

    function fieldSum(names) {
      return names.reduce((total, name) => total + (Number(form.elements[name].value) || 0), 0);
    }

    function updateCompositionChecks() {
      const elemental = fieldSum(elementalFields);
      const structural = fieldSum(structuralFields);
      const elementalOk = Math.abs(elemental - 100) <= compositionTolerance;
      const structuralOk = Math.abs(structural - 100) <= compositionTolerance;
      const elementalEl = document.getElementById('elementalSum');
      const structuralEl = document.getElementById('structuralSum');
      elementalEl.textContent = `Somma C + H + O + N + S + Cl + ceneri: ${elemental.toFixed(2)}%`;
      structuralEl.textContent = `Somma strutturali principali: ${structural.toFixed(2)}%`;
      elementalEl.className = `sum-check ${elementalOk ? 'ok' : 'err'}`;
      structuralEl.className = `sum-check ${structuralOk ? 'ok' : 'err'}`;
      return elementalOk && structuralOk;
    }

    function payloadFromForm() {
      return {
        mass_flow_kg_h: val('mass_flow_kg_h'),
        mass_basis: val('mass_basis'),
        moisture_pct: val('moisture_pct'),
        C_pct: val('C_pct'),
        H_pct: val('H_pct'),
        O_pct: val('O_pct'),
        N_pct: val('N_pct'),
        S_pct: val('S_pct'),
        Cl_pct: val('Cl_pct'),
        ash_pct: val('ash_pct'),
        cellulose_pct: val('cellulose_pct'),
        hemicellulose_pct: val('hemicellulose_pct'),
        lignin_pct: val('lignin_pct'),
        extractives_pct: val('extractives_pct'),
        plastics_pct: val('plastics_pct'),
        pe_pp_pct: val('pe_pp_pct'),
        ps_pct: val('ps_pct'),
        pet_pct: val('pet_pct'),
        pvc_pct: val('pvc_pct'),
        other_organics_pct: val('other_organics_pct'),
        lhv_mj_kg: val('lhv_mj_kg'),
        hhv_mj_kg: val('hhv_mj_kg'),
        temperature_c: val('temperature_c'),
        pressure_bar: val('pressure_bar'),
        residence_time_s: val('residence_time_s'),
        er: val('er'),
        o2_flow_kmol_h: val('o2_flow_kmol_h'),
        agent: val('agent'),
        steam_biomass_ratio: val('steam_biomass_ratio'),
        model: val('model'),
        thermal_mode: val('thermal_mode'),
        external_heat_input_kw: val('external_heat_input_kw'),
        syngas_cooler_outlet_c: val('syngas_cooler_outlet_c'),
        heat_exchanger_effectiveness: val('heat_exchanger_effectiveness'),
        catalyst_type: val('catalyst_type'),
        catalyst_to_biomass_ratio: val('catalyst_to_biomass_ratio'),
        catalyst_activity: val('catalyst_activity'),
        gasifier_type: val('gasifier_type'),
        syngas_cooling_time_s: val('syngas_cooling_time_s'),
        reduction_zone_severity: val('reduction_zone_severity')
      };
    }

    function fmt(value, digits = 3) {
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      if (Math.abs(value) >= 1000) return Number(value).toFixed(1);
      if (Math.abs(value) >= 100) return Number(value).toFixed(2);
      return Number(value).toFixed(digits);
    }

    function tableFromObject(tableId, data, unit = '') {
      const rows = Object.entries(data || {})
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => `<tr><td>${k}</td><td>${fmt(v)}</td><td>${unit}</td></tr>`)
        .join('');
      document.getElementById(tableId).innerHTML = `<thead><tr><th>Voce</th><th>Valore</th><th>Unità</th></tr></thead><tbody>${rows}</tbody>`;
    }

    function tableFromRows(tableId, rows) {
      document.getElementById(tableId).innerHTML = `<thead><tr><th>Voce</th><th>Valore</th><th>Unità</th></tr></thead><tbody>${
        rows.map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td><td>${row[2] || ''}</td></tr>`).join('')
      }</tbody>`;
    }

    function renderGasTable(result) {
      const isWet = gasBasis === 'wet';
      const data = isWet ? result.gas.wet_species_flows : result.gas.dry_species_flows;
      const rows = Object.entries(data || {})
        .sort((a, b) => (b[1].mol_pct || 0) - (a[1].mol_pct || 0))
        .map(([species, values]) => `
          <tr>
            <td>${species}</td>
            <td>${fmt(values.mol_pct)}</td>
            <td>${fmt(values.nm3_h)}</td>
            <td>${fmt(values.kg_h)}</td>
            <td>${fmt(values.kmol_h)}</td>
          </tr>
        `).join('');
      document.getElementById('gasTableTitle').textContent = isWet ? 'Gas umido' : 'Gas secco';
      document.getElementById('gasDryToggle').classList.toggle('active', !isWet);
      document.getElementById('gasWetToggle').classList.toggle('active', isWet);
      document.getElementById('gasTable').innerHTML = `
        <thead><tr><th>Specie</th><th>% mol</th><th>Nm3/h</th><th>kg/h</th><th>kmol/h</th></tr></thead>
        <tbody>${rows}</tbody>
      `;
    }

    function render(result) {
      latestResult = result;
      document.getElementById('dryFlow').textContent = `${fmt(result.gas.dry_flow_nm3_h, 1)} Nm3/h`;
      document.getElementById('lhv').textContent = `${fmt(result.gas.lhv_mj_nm3_dry, 2)} MJ/Nm3`;
      document.getElementById('charYield').textContent = `${fmt(result.yields.char_kg_h, 2)} kg/h`;
      document.getElementById('cge').textContent = `${fmt(result.gas.cold_gas_efficiency_pct, 1)} / ${fmt(result.energy_balance.overall_efficiency_pct, 1)} %`;
      renderGasTable(result);
      tableFromRows('yieldTable', [
        ['Char', fmt(result.yields.char_kg_h), 'kg/h'],
        ['Resa char', fmt(result.yields.char_pct_dry_feed), '% massa secca'],
        ['Tar/CnHm', fmt(result.yields.tar_cnhm_kg_h), 'kg/h'],
        ['Resa tar/CnHm', fmt(result.yields.tar_pct_dry_feed), '% massa secca'],
        ['Gas secco', fmt(result.gas.dry_flow_nm3_h), 'Nm3/h'],
        ['Gas umido', fmt(result.gas.wet_flow_nm3_h), 'Nm3/h'],
        ['Aria', fmt(result.oxidant.air_in_kg_h), 'kg/h'],
        ['Aria', fmt(result.oxidant.air_in_nm3_h), 'Nm3/h'],
        ['Aria specifica', fmt(result.oxidant.air_in_kg_per_kg_dry_feed), 'kg/kg secco'],
        ['O2', fmt(result.oxidant.o2_in_kmol_h), 'kmol/h'],
        ['N2', fmt(result.oxidant.n2_in_kmol_h), 'kmol/h'],
        ['ER', fmt(result.oxidant.er), '-']
      ]);
      tableFromRows('energyAirTable', [
        ['PCS feed', fmt(result.feedstock_energy?.hhv_pcs_mj_kg_dry, 3), 'MJ/kg secco'],
        ['PCI feed', fmt(result.feedstock_energy?.lhv_pci_mj_kg_dry, 3), 'MJ/kg secco'],
        ['PCS metodo', result.feedstock_energy?.hhv_pcs_method || '-', ''],
        ['PCS Channiwala-Parikh', fmt(result.feedstock_energy?.hhv_correlation_comparison?.channiwala_parikh_mj_kg_dry, 3), 'MJ/kg secco'],
        ['PCS Dulong', fmt(result.feedstock_energy?.hhv_correlation_comparison?.dulong_mj_kg_dry, 3), 'MJ/kg secco'],
        ['Aria stechiometrica', fmt(result.oxidant.stoich_air_kg_h, 2), 'kg/h'],
        ['Aria stechiometrica', fmt(result.oxidant.stoich_air_nm3_h, 2), 'Nm3/h'],
        ['Aria stechiometrica specifica', fmt(result.oxidant.stoich_air_kg_per_kg_dry_feed, 3), 'kg/kg secco'],
        ['Aria gassificazione a ER', fmt(result.oxidant.air_in_kg_h, 2), 'kg/h'],
        ['Aria gassificazione a ER', fmt(result.oxidant.air_in_nm3_h, 2), 'Nm3/h'],
        ['Metodo aria', result.oxidant.air_calculation_method || '-', ''],
        ['Regime termico', result.energy_balance.thermal_mode, ''],
        ['Potenza chimica feedstock', fmt(result.energy_balance.feedstock_chemical_power_lhv_kw, 2), 'kW PCI'],
        ['Potenza chimica syngas', fmt(result.energy_balance.syngas_chemical_power_lhv_kw, 2), 'kW PCI'],
        ['Potenza termica esterna', fmt(result.energy_balance.external_thermal_input_kw, 2), 'kW'],
        ['Calore sensibile disponibile', fmt(result.energy_balance.syngas_sensible_heat_available_kw, 2), 'kW'],
        ['Recupero termico utile', fmt(result.energy_balance.thermal_recovery_kw, 2), 'kW'],
        ['Efficienza scambiatore', fmt(100 * result.energy_balance.heat_exchanger_effectiveness, 1), '%'],
        ['Overall efficiency', fmt(result.energy_balance.overall_efficiency_pct, 1), '%']
      ]);
      const catalyst = result.catalyst || {};
      const delta = catalyst.comparison_vs_no_catalyst || {};
      tableFromRows('catalystTable', [
        ['Tipo', catalyst.type || 'none', ''],
        ['Rapporto catalizzatore/biomassa', fmt(catalyst.catalyst_to_biomass_ratio_kg_kg_dry), 'kg/kg secco'],
        ['Attività relativa', fmt(catalyst.relative_activity_0_1), '0-1'],
        ['Severità effettiva', fmt(catalyst.effective_severity_0_1), '0-1'],
        ['Conversione tar modellata', fmt(catalyst.modeled_tar_conversion_pct), '%'],
        ['Portata syngas vs. no catalyst', fmt(delta.dry_syngas_flow_change_pct), '%'],
        ['Resa tar vs. no catalyst', fmt(delta.tar_yield_change_pct), '%'],
        ['H2 secco vs. no catalyst', fmt(delta.h2_dry_mol_pct_change), 'punti % mol'],
        ['CO secco vs. no catalyst', fmt(delta.co_dry_mol_pct_change), 'punti % mol'],
        ['CH4 secco vs. no catalyst', fmt(delta.ch4_dry_mol_pct_change), 'punti % mol'],
        ['CGE vs. no catalyst', fmt(delta.cge_percentage_point_change), 'punti %'],
        ['Overall vs. no catalyst', fmt(delta.overall_efficiency_percentage_point_change), 'punti %']
      ]);
      const reactor = result.reactor || {};
      tableFromRows('reactorTable', [
        ['Configurazione', reactor.gasifier_type || 'generic', ''],
        ['Moltiplicatore target char', fmt(reactor.char_target_multiplier), '-'],
        ['Moltiplicatore target tar', fmt(reactor.tar_target_multiplier), '-'],
        ['Base', reactor.basis || '-', '']
      ]);
      tableFromRows('balanceTable', [
        ['Massa in ingresso', fmt(result.balances.mass.in_kg_h), 'kg/h'],
        ['Massa in uscita', fmt(result.balances.mass.out_kg_h), 'kg/h'],
        ['Errore relativo massa', fmt(result.balances.mass.rel_error * 100, 6), '%'],
        ['Bilancio di massa', result.balances.mass.ok ? 'OK' : 'NO', ''],
        ['Bilancio atomico', result.balances.atomic.ok ? 'OK' : 'NO', '']
      ]);
      const trace = result.gas.trace_pollutants || {};
      const temperatureRisk = trace.temperature_sensitivity?.post_gasifier_de_novo_risk_index_by_temperature_c || {};
      tableFromRows('traceTable', [
        ['PCDD/F rischio', trace.dioxins_furans_risk || '-', 'classe'],
        ['PCDD/F index', fmt(trace.dioxins_furans_index_0_1), '0-1'],
        ['Severità zona riducente', fmt(trace.main_drivers?.reduction_zone_severity), '0-1'],
        ['Fattore residuo NOx/N2O', fmt(trace.main_drivers?.nox_reduction_factor), '-'],
        ['Fattore residuo NH3/HCN', fmt(trace.main_drivers?.nh3_hcn_reduction_factor), '-'],
        ['PCDD/F TEQ', (trace.pcdd_f_teq_ng_i_teq_nm3_screening_range || []).map(v => fmt(v, 4)).join(' - '), 'ng I-TEQ/Nm3'],
        ['PCDD/F totale', (trace.total_pcdd_f_ng_nm3_screening_range || []).map(v => fmt(v, 4)).join(' - '), 'ng/Nm3'],
        ['Sopravvivenza PCDD/F nel reattore', fmt(trace.temperature_sensitivity?.in_reactor_pcdd_f_survival_index_0_1), '0-1'],
        ...Object.entries(temperatureRisk).map(([temperature, index]) => [
          `Rischio de novo a ${temperature} C`, fmt(index), '0-1'
        ]),
        ['Base', trace.basis || '-', '']
      ]);
      tableFromObject('charTable', result.char?.component_breakdown_wt_pct || {}, '% massa');
      document.getElementById('warnings').innerHTML = (result.warnings || []).map(w => `<li>${w}</li>`).join('');
      document.getElementById('jsonOut').textContent = JSON.stringify(result, null, 2);
      refreshDownloads();
      statusEl.textContent = 'OK';
      statusEl.className = 'status ok';
    }

    document.getElementById('gasDryToggle').addEventListener('click', () => {
      gasBasis = 'dry';
      if (latestResult) renderGasTable(latestResult);
    });
    document.getElementById('gasWetToggle').addEventListener('click', () => {
      gasBasis = 'wet';
      if (latestResult) renderGasTable(latestResult);
    });

    function refreshDownloads() {
      if (!latestResult) return;
      jsonUrl = `/download/json?t=${Date.now()}`;
      csvUrl = `/download/csv?t=${Date.now()}`;
      downloadJson.href = jsonUrl;
      downloadJson.download = 'gasifier_result.json';
      downloadJson.classList.remove('disabled');
      downloadCsv.href = csvUrl;
      downloadCsv.download = 'gasifier_result.csv';
      downloadCsv.classList.remove('disabled');
    }

    async function simulate() {
      if (!updateCompositionChecks()) {
        statusEl.textContent = 'Le composizioni elementare e strutturale devono sommare al 100% (tolleranza ±0,5%).';
        statusEl.className = 'status err';
        return;
      }
      statusEl.textContent = 'Running';
      statusEl.className = 'status';
      for (const button of document.querySelectorAll('button')) button.disabled = true;
      downloadJson.classList.add('disabled');
      downloadCsv.classList.add('disabled');
      try {
        const response = await fetch('/api/simulate', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payloadFromForm())
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Simulation failed');
        latestCsv = data.csv;
        render(data.result);
      } catch (err) {
        statusEl.textContent = err.message;
        statusEl.className = 'status err';
      } finally {
        for (const button of document.querySelectorAll('button')) button.disabled = false;
        if (latestResult) {
          downloadJson.classList.remove('disabled');
          downloadCsv.classList.remove('disabled');
        }
      }
    }

    form.addEventListener('submit', event => {
      event.preventDefault();
      simulate();
    });
    form.addEventListener('input', updateCompositionChecks);
    document.getElementById('resetExample').addEventListener('click', () => {
      form.reset();
      updateCompositionChecks();
      simulate();
    });
    updateCompositionChecks();
    simulate();
  </script>
</body>
</html>
"""


class GasifierWebHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the web UI and JSON API."""

    server_version = "BiomassGasifierWeb/1.0"

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_download(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload, indent=2).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        """Serve the single-page application or the example payload."""
        path = urlparse(self.path).path
        if path == "/":
            self._send(HTTPStatus.OK, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/example":
            self._send_json(HTTPStatus.OK, DEFAULT_INPUT)
            return
        if path == "/download/json":
            if LAST_RESULT is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "no simulation result available"})
                return
            self._send_download(
                json.dumps(LAST_RESULT, indent=2).encode("utf-8"),
                "application/json; charset=utf-8",
                "gasifier_result.json",
            )
            return
        if path == "/download/csv":
            if not LAST_CSV:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "no simulation result available"})
                return
            self._send_download(LAST_CSV.encode("utf-8"), "text/csv; charset=utf-8", "gasifier_result.csv")
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        """Run a simulation from a JSON payload."""
        path = urlparse(self.path).path
        if path != "/api/simulate":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            global LAST_RESULT, LAST_CSV
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = simulate_from_payload(payload)
            csv_text = result_to_csv(result)
            LAST_RESULT = result
            LAST_CSV = csv_text
            try:
                request_count = record_request(
                    LOCAL_LOG_DIR,
                    self.client_address[0],
                    self.headers.get("User-Agent", ""),
                    path,
                    "200 OK",
                )
                tracking = {"request_count": request_count}
            except OSError as log_exc:
                tracking = {"warning": f"Request log unavailable: {log_exc}"}
            self._send_json(
                HTTPStatus.OK,
                {"result": result, "csv": csv_text, "tracking": tracking},
            )
        except Exception as exc:
            try:
                record_request(
                    LOCAL_LOG_DIR,
                    self.client_address[0],
                    self.headers.get("User-Agent", ""),
                    path,
                    "400 Bad Request",
                )
            except OSError:
                pass
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        """Keep server logs concise."""
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    """Run the web server."""
    parser = argparse.ArgumentParser(description="Serve the biomass gasifier web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), GasifierWebHandler)
    print(f"Serving Biomass Gasifier on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
