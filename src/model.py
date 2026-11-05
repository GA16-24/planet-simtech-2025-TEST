#!/usr/bin/env python3
"""Wärmebilanz und Auslegung der Blautopf-Wärmeschleuse.

Nur Python-Standardbibliothek. Alle Zeiten werden intern in Jahren gerechnet.
"""

import argparse
import csv
import json
import math
from pathlib import Path

RHO = 998.0  # kg/m3, Wasser bei etwa 10 °C
CP = 4182.0  # J/(kg K)
T0 = 9.0  # °C, natürliche Quelltemperatur
T_BOIL = 98.3  # °C, gerundet bei 512 m Höhe
T_TARGET = 12.0  # °C, technische Obergrenze
T_NORMAL = 9.5  # °C, betrieblicher Sollwert
Q_MEAN = 2.270  # m3/s, LGRB
Q_MIN = 0.250  # m3/s, LGRB
Q_MAX = 32.670  # m3/s, LGRB
YEARS_TO_BOIL = 10.0
SECONDS_PER_YEAR = 365.25 * 24 * 3600

H10 = RHO * CP * Q_MEAN * (T_BOIL - T0)
HOT_RATE = H10 / YEARS_TO_BOIL
CAPEX_BREAKDOWN_MEUR = {
    "erkundung_messnetz": 30.0,
    "bohrungen_hydraulik": 120.0,
    "waermetauscher": 60.0,
    "trockenkuehler": 80.0,
    "nachkuehlmodule": 60.0,
    "netz_leittechnik_notstrom": 130.0,
    "reserve": 20.0,
}


def heat_input(year):
    return HOT_RATE * year


def liquid_temperature_before_capping(year, flow):
    return T0 + heat_input(year) / (RHO * CP * flow)


def natural_temperature(year, flow):
    return min(T_BOIL, liquid_temperature_before_capping(year, flow))


def boiling_year(flow):
    return YEARS_TO_BOIL * flow / Q_MEAN


def required_cooling(year, flow, target=T_TARGET):
    return max(0.0, heat_input(year) - RHO * CP * flow * (target - T0))


def exact_threshold_year(capacity, flow, model="B"):
    year10 = 10.0
    year11 = 11.0
    required10 = required_cooling_model(year10, flow, T_TARGET, model)
    annual_increase = required_cooling_model(year11, flow, T_TARGET, model) - required10
    return year10 + (capacity - required10) / annual_increase


def required_cooling_temperature_slope(year, flow, target=T_TARGET):
    raw = T0 + (T_BOIL - T0) * year / YEARS_TO_BOIL
    return RHO * CP * flow * max(0.0, raw - target)


def raw_temperature(year, flow, model="B"):
    if model == "B":
        return T0 + (T_BOIL - T0) * year / YEARS_TO_BOIL
    return liquid_temperature_before_capping(year, flow)


def required_cooling_model(year, flow, target=T_TARGET, model="B"):
    if model == "B":
        return required_cooling_temperature_slope(year, flow, target)
    return required_cooling(year, flow, target)


def controlled_temperature(year, flow, capacity, target=T_TARGET, model="B"):
    removed = min(capacity, required_cooling_model(year, flow, target, model))
    return raw_temperature(year, flow, model) - removed / (RHO * CP * flow)


def required_modules(year, model="B"):
    flow = Q_MAX if model == "B" else Q_MEAN
    required = required_cooling_model(year, flow, T_NORMAL, model)
    if model == "B" and year >= 20:
        baseline = 321
    elif model == "B" and year >= 10:
        baseline = 160
    elif model == "A" and year >= 10:
        baseline = 13
    else:
        baseline = 3
    return max(3, baseline, math.ceil(required / 80e6) + 1)


def carnot_cooling_cop(t_cold_c=7.0, t_hot_c=45.0):
    return (t_cold_c + 273.15) / (t_hot_c - t_cold_c)


def real_cooling_cop():
    return 0.55 * carnot_cooling_cop()


def required_process_flow(flow, raw, cooled=9.5, target=T_TARGET):
    if raw <= target:
        return 0.0
    return flow * (raw - target) / (raw - cooled)


def monthly_design(flow=Q_MEAN, capacity=None, year=10.0, target=T_NORMAL,
                   approach=10.0, fan_fraction=0.01, head=140.0, model="B"):
    """Monatsmodell mit Wärmeabfuhr, Kondensatorlast und Hilfsenergie."""
    if capacity is None:
        capacity = (160 if model == "B" else 13) * 80e6
    air_temperatures = [0.0, 1.0, 4.0, 8.0, 13.0, 16.0, 18.0, 18.0, 14.0, 9.0, 4.0, 1.0]
    month_hours = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    cop = real_cooling_cop()
    raw = raw_temperature(year, flow, model)
    process_flow = required_process_flow(flow, raw, cooled=target, target=target)
    pump_mw = RHO * 9.81 * process_flow * head / 0.75 / 1e6
    rows = []
    for month, (air, hours) in enumerate(zip(air_temperatures, month_hours), start=1):
        heat = min(capacity, required_cooling_model(year, flow, target, model))
        dry_outlet = max(target, min(raw, air + approach))
        dry = min(heat, RHO * CP * flow * max(0.0, raw - dry_outlet))
        trim = heat - dry
        trim_electric_mw = trim / 1e6 / cop
        condenser_mw = (trim + trim_electric_mw * 1e6) / 1e6
        rejected_mw = dry / 1e6 + condenser_mw
        fan_mw = fan_fraction * rejected_mw
        electric_mw = trim_electric_mw + fan_mw + pump_mw
        outlet_c = raw - heat / (RHO * CP * flow)
        rows.append({
            "month": month,
            "air_c": air,
            "hours": hours,
            "raw_c": raw,
            "outlet_c": outlet_c,
            "process_flow_m3s": process_flow,
            "heat_removed_mw": heat / 1e6,
            "dry_cooling_mw": dry / 1e6,
            "trim_cooling_mw": trim / 1e6,
            "condenser_mw": condenser_mw,
            "rejected_mw": rejected_mw,
            "trim_electric_mw": trim_electric_mw,
            "fan_mw": fan_mw,
            "pump_mw": pump_mw,
            "electric_mw": electric_mw,
            "electric_gwh": electric_mw * hours / 1000.0,
        })
    return rows


def economics(rows, capex_eur=500e6, electricity_eur_mwh=120.0,
              maintenance_fraction=0.025, heat_sales_gwh=0.0,
              heat_price_eur_mwh=45.0, years=20, discount=0.03,
              replacement_eur=100e6, replacement_year=15):
    electricity_gwh = sum(row["electric_gwh"] for row in rows)
    trim_gwh = sum(row["trim_electric_mw"] * row["hours"] / 1000.0 for row in rows)
    fan_gwh = sum(row["fan_mw"] * row["hours"] / 1000.0 for row in rows)
    pump_gwh = sum(row["pump_mw"] * row["hours"] / 1000.0 for row in rows)
    annual_cost = electricity_gwh * 1000 * electricity_eur_mwh
    annual_cost += capex_eur * maintenance_fraction
    annual_revenue = heat_sales_gwh * 1000 * heat_price_eur_mwh
    annuity = (1 - (1 + discount) ** (-years)) / discount
    npv = capex_eur + annuity * (annual_cost - annual_revenue)
    npv += replacement_eur / (1 + discount) ** replacement_year
    return {
        "capex_meur": capex_eur / 1e6,
        "annual_trim_gwh": trim_gwh,
        "annual_fan_gwh": fan_gwh,
        "annual_pump_gwh": pump_gwh,
        "annual_electricity_gwh": electricity_gwh,
        "annual_cost_meur": annual_cost / 1e6,
        "annual_heat_revenue_meur": annual_revenue / 1e6,
        "replacement_meur": replacement_eur / 1e6,
        "present_cost_20y_meur": npv / 1e6,
    }


def growth_economics(electricity_eur_mwh=120.0, discount=0.03,
                     module_eur=30e6, constant_after_year=None,
                     monthly_options=None, model="B", fixed_eur=110e6):
    modules = 3
    monthly_options = dict(monthly_options or {})
    monthly_options.setdefault("flow", Q_MAX if model == "B" else Q_MEAN)
    monthly_options["model"] = model
    npv = fixed_eur + modules * module_eur
    schedule = []
    replacement_eur = 0.0
    for year in range(1, 21):
        design_year = min(year, constant_after_year) if constant_after_year else year
        needed = required_modules(design_year, model)
        new_modules = max(0, needed - modules)
        modules = max(modules, needed)
        expansion = new_modules * module_eur
        npv += expansion / (1 + discount) ** (year - 1)
        rows = monthly_design(capacity=math.inf, year=design_year, **monthly_options)
        electricity_gwh = sum(row["electric_gwh"] for row in rows)
        maintenance = 0.025 * (fixed_eur + modules * module_eur)
        operating = electricity_gwh * 1000 * electricity_eur_mwh + maintenance
        if year == 1:
            operating += 50e6
        if year == 15:
            replacement_eur = 200e6 * modules / 13
        npv += operating / (1 + discount) ** year
        schedule.append({
            "year": year,
            "modules": modules,
            "new_modules": new_modules,
            "electricity_gwh": electricity_gwh,
            "operating_meur": operating / 1e6,
        })
    npv += replacement_eur / (1 + discount) ** 15
    return {
        "present_cost_20y_meur": npv / 1e6,
        "replacement_meur": replacement_eur / 1e6,
        "schedule": schedule,
    }


def write_svg(path, title, x_label, y_label, series, width=900, height=540,
              secondary_series=None, secondary_y_label=""):
    secondary_series = secondary_series or []
    left = 160
    right = 150 if secondary_series else 30
    top = 200 if len(series) + len(secondary_series) >= 3 else 60
    bottom = 90
    pw, ph = width - left - right, height - top - bottom
    all_points = [point for _, points, _ in series for point in points]
    xmin = min(p[0] for p in all_points)
    xmax = max(p[0] for p in all_points)
    ymin = min(0.0, min(p[1] for p in all_points))

    def rounded_axis(value):
        rough_step = value / 5
        magnitude = 10 ** math.floor(math.log10(rough_step))
        step = next(
            magnitude * factor
            for factor in (1, 2, 2.5, 5, 10)
            if rough_step <= magnitude * factor
        )
        return 5 * step, step

    ymax, y_step = rounded_axis(max(p[1] for p in all_points))
    if secondary_series:
        secondary_max, secondary_step = rounded_axis(
            max(p[1] for _, points, _ in secondary_series for p in points)
        )

    def sx(x):
        return left + (x - xmin) / (xmax - xmin) * pw

    def sy(y):
        return top + (ymax - y) / (ymax - ymin) * ph

    def sy_secondary(y):
        return top + (secondary_max - y) / secondary_max * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#18242c;font-size:36px}.title{font-size:42px;font-weight:700}.grid{stroke:#dce3e8;stroke-width:1}.axis{stroke:#536570;stroke-width:1.5}</style>',
        f'<text class="title" x="{left}" y="45">{title}</text>',
    ]
    for i in range(round(ymax / y_step) + 1):
        value = i * y_step
        y = sy(value)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}"/>')
        parts.append(f'<text x="{left-10}" y="{y+5:.2f}" text-anchor="end">{value:.0f}</text>')
    for i in range(6):
        value = xmin + (xmax - xmin) * i / 5
        x = sx(value)
        parts.append(f'<line class="grid" x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{height-bottom}"/>')
        parts.append(f'<text x="{x:.2f}" y="{height-bottom+25}" text-anchor="middle">{value:.0f}</text>')
    parts.append(f'<line class="axis" x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}"/>')
    parts.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}"/>')
    parts.append(f'<text x="{left+pw/2}" y="{height-15}" text-anchor="middle">{x_label}</text>')
    parts.append(f'<text x="35" y="{top+ph/2}" text-anchor="middle" transform="rotate(-90 35 {top+ph/2})">{y_label}</text>')
    if secondary_series:
        parts.append(f'<line class="axis" x1="{width-right}" y1="{top}" x2="{width-right}" y2="{height-bottom}"/>')
        for i in range(1, round(secondary_max / secondary_step) + 1):
            value = i * secondary_step
            y = sy_secondary(value)
            parts.append(f'<text x="{width-right+10}" y="{y+5:.2f}">{value:.0f}</text>')
        parts.append(f'<text x="{width-25}" y="{top+ph/2}" text-anchor="middle" transform="rotate(90 {width-25} {top+ph/2})">{secondary_y_label}</text>')
    legend_series = series + secondary_series
    for index, (name, points, color) in enumerate(legend_series):
        y_scale = sy_secondary if index >= len(series) else sy
        coords = " ".join(f"{sx(x):.2f},{y_scale(y):.2f}" for x, y in points)
        dash = ' stroke-dasharray="10 7"' if name.startswith("N+1") else ""
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        if len(legend_series) >= 3:
            lx = left + 15 + (index % 2) * 350
            legend_rows = (len(legend_series) + 1) // 2
            ly = top - 50 - (legend_rows - 1) * 40 + (index // 2) * 40
        else:
            lx = left + 15 + index * 245
            ly = top + 18
        parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+25}" y2="{ly}" stroke="{color}" stroke-width="3"{dash}/>')
        parts.append(f'<text x="{lx+32}" y="{ly+5}">{name}</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def run(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    installed_b = 160 * 80e6
    n_plus_one_b = 159 * 80e6
    rows_b = monthly_design(flow=Q_MAX, capacity=installed_b, model="B")
    rows_b_mean = monthly_design(flow=Q_MEAN, capacity=installed_b, model="B")
    rows_a = monthly_design(flow=Q_MEAN, capacity=13 * 80e6, model="A")
    growth_b = growth_economics(model="B")
    stationary_b = growth_economics(model="B", constant_after_year=10)
    growth_b_mean = growth_economics(model="B", monthly_options={"flow": Q_MEAN})
    stationary_b_mean = growth_economics(model="B", monthly_options={"flow": Q_MEAN}, constant_after_year=10)
    growth_a = growth_economics(model="A")
    stationary_a = growth_economics(model="A", constant_after_year=10)
    growth_a_max = growth_economics(model="A", monthly_options={"flow": Q_MAX}, fixed_eur=200e6)
    stationary_a_max = growth_economics(
        model="A", monthly_options={"flow": Q_MAX}, constant_after_year=10, fixed_eur=200e6
    )
    stationary_b_low = growth_economics(
        model="B", monthly_options={"flow": Q_MIN}, constant_after_year=10
    )
    rows_b_low = monthly_design(flow=Q_MIN, capacity=installed_b, model="B")

    with (output_dir / "verlauf.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["jahr", "natur_max_c", "bedarf_max_mw", "geregelt_12800mw_c", "geregelt_nplus1_12720mw_c", "natur_a_mittel_c", "bedarf_a_niedrig_mw"])
        for step in range(201):
            year = step / 10
            writer.writerow([
                year, raw_temperature(year, Q_MAX, "B"),
                required_cooling_model(year, Q_MAX, T_TARGET, "B") / 1e6,
                controlled_temperature(year, Q_MAX, installed_b, T_TARGET, "B"),
                controlled_temperature(year, Q_MAX, n_plus_one_b, T_TARGET, "B"),
                natural_temperature(year, Q_MEAN),
                required_cooling(year, Q_MIN) / 1e6,
            ])

    with (output_dir / "monate.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_b[0]))
        writer.writeheader()
        writer.writerows(rows_b)
    with (output_dir / "monate-mittel.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_b_mean[0]))
        writer.writeheader()
        writer.writerows(rows_b_mean)
    with (output_dir / "monate-waermeleistung.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_a[0]))
        writer.writeheader()
        writer.writerows(rows_a)
    with (output_dir / "monate-niedrig.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_b_low[0]))
        writer.writeheader()
        writer.writerows(rows_b_low)
    with (output_dir / "ausbau.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(growth_b["schedule"][0]))
        writer.writeheader()
        writer.writerows(growth_b["schedule"])
    with (output_dir / "konstant.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stationary_b["schedule"][0]))
        writer.writeheader()
        writer.writerows(stationary_b["schedule"])
    with (output_dir / "ausbau-waermeleistung.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(growth_a["schedule"][0]))
        writer.writeheader()
        writer.writerows(growth_a["schedule"])

    years = [step / 10 for step in range(201)]
    write_svg(
        output_dir / "temperaturverlauf.svg",
        "Temperaturtrend bei maximalem Abfluss",
        "Zeit in Jahren", "Temperatur in °C",
        [
            ("Natur bis Sieden", [(y, raw_temperature(y, Q_MAX, "B")) for y in years if y <= 10], "#d1495b"),
            ("12,8 GW fest", [(y, controlled_temperature(y, Q_MAX, installed_b, T_TARGET, "B")) for y in years], "#00798c"),
            ("N+1: 12,72 GW", [(y, controlled_temperature(y, Q_MAX, n_plus_one_b, T_TARGET, "B")) for y in years], "#edae49"),
            ("Ausbau", [(y, controlled_temperature(y, Q_MAX, required_modules(y, "B") * 80e6, T_NORMAL, "B")) for y in years], "#6a8b59"),
            ("Grenze", [(y, T_TARGET) for y in years], "#384d48"),
        ],
    )
    write_svg(
        output_dir / "schuettung.svg",
        "Alternative A: Wärmeleistung wächst linear",
        "Zeit in Jahren", "Temperatur in °C",
        [
            ("Minimum", [(y, natural_temperature(y, Q_MIN)) for y in years if y <= boiling_year(Q_MIN)], "#d1495b"),
            ("Mittel", [(y, natural_temperature(y, Q_MEAN)) for y in years if y <= boiling_year(Q_MEAN)], "#edae49"),
            ("Maximum", [(y, natural_temperature(y, Q_MAX)) for y in years if y <= boiling_year(Q_MAX)], "#00798c"),
        ],
    )
    write_svg(
        output_dir / "kaelte-monate.svg",
        "Kaskade, Jahr 10, maximaler Abfluss",
        "Monat", "Wärmeleistung in MW",
        [
            ("Trockenkühlung", [(r["month"], r["dry_cooling_mw"]) for r in rows_b], "#00798c"),
            ("Nachkühlung", [(r["month"], r["trim_cooling_mw"]) for r in rows_b], "#edae49"),
        ],
        secondary_series=[
            ("Strom mit Hilfsenergie", [(r["month"], r["electric_mw"]) for r in rows_b], "#d1495b"),
        ],
        secondary_y_label="Elektrische Leistung in MW",
    )

    process_b = required_process_flow(Q_MAX, T_BOIL)
    annual_b = economics(rows_b, capex_eur=4910e6)
    annual_b["present_cost_20y_meur"] = stationary_b["present_cost_20y_meur"]
    annual_b["replacement_meur"] = stationary_b["replacement_meur"]
    annual_b_mean = economics(rows_b_mean, capex_eur=4910e6)
    annual_b_mean["present_cost_20y_meur"] = stationary_b_mean["present_cost_20y_meur"]
    annual_b_mean["replacement_meur"] = stationary_b_mean["replacement_meur"]
    annual_a = economics(rows_a)
    annual_a["present_cost_20y_meur"] = stationary_a["present_cost_20y_meur"]
    annual_a["replacement_meur"] = stationary_a["replacement_meur"]
    annual_b_low = economics(rows_b_low, capex_eur=4910e6)
    annual_b_low["present_cost_20y_meur"] = stationary_b_low["present_cost_20y_meur"]
    annual_b_low["replacement_meur"] = stationary_b_low["replacement_meur"]
    annual_a_max = economics(
        monthly_design(flow=Q_MAX, capacity=13 * 80e6, model="A"), capex_eur=590e6
    )
    annual_a_max["present_cost_20y_meur"] = stationary_a_max["present_cost_20y_meur"]
    annual_a_max["replacement_meur"] = stationary_a_max["replacement_meur"]
    annuity = (1 - 1.03 ** -20) / 0.03
    low_yield_npv_b = stationary_b["present_cost_20y_meur"] + 440.0 + 0.025 * 440.0 * annuity
    energy_sensitivity = {}
    for name, options in [
        ("approach_5k", {"approach": 5.0}),
        ("approach_12k", {"approach": 12.0}),
        ("fan_2_percent", {"fan_fraction": 0.02}),
        ("head_100m", {"head": 100.0}),
    ]:
        energy_sensitivity[name] = sum(
            row["electric_gwh"] for row in monthly_design(flow=Q_MAX, capacity=math.inf, model="B", **options)
        )
    summary = {
        "baseline_model": "B",
        "baseline_cooling_year10_min_mw": required_cooling_model(10.0, Q_MIN, T_TARGET, "B") / 1e6,
        "baseline_cooling_year10_mean_mw": required_cooling_model(10.0, Q_MEAN, T_TARGET, "B") / 1e6,
        "baseline_cooling_year10_max_mw": required_cooling_model(10.0, Q_MAX, T_TARGET, "B") / 1e6,
        "baseline_normal_cooling_year10_max_mw": required_cooling_model(10.0, Q_MAX, T_NORMAL, "B") / 1e6,
        "baseline_installed_modules": 160,
        "baseline_module_capacity_mw": 80.0,
        "baseline_installed_capacity_mw": installed_b / 1e6,
        "baseline_n_plus_one_capacity_mw": n_plus_one_b / 1e6,
        "baseline_n_plus_one_reserve_normal_percent": (n_plus_one_b / required_cooling_model(10.0, Q_MAX, T_NORMAL, "B") - 1) * 100,
        "baseline_capex_meur": 110.0 + 160 * 30.0,
        "baseline_process_flow_year10_max_m3s": process_b,
        "baseline_bypass_flow_year10_max_m3s": Q_MAX - process_b,
        "baseline_pump_power_year10_max_mw": RHO * 9.81 * process_b * 140.0 / 0.75 / 1e6,
        "baseline_well_pairs": math.ceil(Q_MAX / 1.55) + 1,
        "baseline_low_yield_well_pairs": math.ceil(Q_MAX / 0.5) + 1,
        "baseline_low_yield_npv_constant_meur": low_yield_npv_b,
        "baseline_year20_modules": required_modules(20.0, "B"),
        "baseline_year20_n_plus_one_capacity_gw": (required_modules(20.0, "B") - 1) * 0.080,
        "baseline_year20_n_plus_one_reserve_normal_percent": ((required_modules(20.0, "B") - 1) * 80e6 / required_cooling_model(20.0, Q_MAX, T_NORMAL, "B") - 1) * 100,
        "baseline_year20_capex_meur": 110.0 + required_modules(20.0, "B") * 30.0,
        "baseline_growth_with_source_control_meur": growth_b["present_cost_20y_meur"] + 250.0 / 1.03 ** 10,
        "source_control_scenario": {
            "method": "Erkundungsbohrung, Packer und Verpressung des heißen Zuflusses",
            "cost_meur": 250.0,
            "feasibility_gate": "Nur nach nachgewiesener Lage, Dichtheit und Druckbeständigkeit",
        },
        "baseline_installed_threshold_year": next(
            y for y in years if controlled_temperature(y, Q_MAX, installed_b, T_TARGET, "B") > T_TARGET + 1e-9
        ),
        "baseline_n_plus_one_threshold_year": next(
            y for y in years if controlled_temperature(y, Q_MAX, n_plus_one_b, T_TARGET, "B") > T_TARGET + 1e-9
        ),
        "baseline_exact_installed_threshold_year": exact_threshold_year(installed_b, Q_MAX, "B"),
        "baseline_exact_n_plus_one_threshold_year": exact_threshold_year(n_plus_one_b, Q_MAX, "B"),
        "baseline_annual_max": annual_b,
        "baseline_annual_mean": annual_b_mean,
        "baseline_annual_low": annual_b_low,
        "baseline_steady_annual_cost_meur": annual_b["annual_cost_meur"] + stationary_b["replacement_meur"] / 15.0,
        "baseline_growth": growth_b,
        "baseline_stationary": stationary_b,
        "baseline_mean_growth": growth_b_mean,
        "baseline_mean_stationary": stationary_b_mean,
        "baseline_low_stationary": stationary_b_low,
        "baseline_backup_gw": 7.0,
        "baseline_grid_feed_gw": 7.5,
        "energy_sensitivity_gwh": energy_sensitivity,
        "alternative_a": {
            "h10_mw": H10 / 1e6,
            "cooling_year10_min_mw": required_cooling(10.0, Q_MIN) / 1e6,
            "cooling_year10_mean_mw": required_cooling(10.0, Q_MEAN) / 1e6,
            "cooling_year10_max_mw": required_cooling(10.0, Q_MAX) / 1e6,
            "annual_mean": annual_a,
            "annual_max": annual_a_max,
            "mathematical_stress_growth_not_design": growth_a,
            "stationary": stationary_a,
            "mathematical_stress_growth_max_not_design": growth_a_max,
            "stationary_max": stationary_a_max,
            "capex_breakdown_meur": CAPEX_BREAKDOWN_MEUR,
        },
    }
    (output_dir / "kennwerte.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    assert math.isclose(summary["baseline_cooling_year10_max_mw"], 11767.236984756, rel_tol=1e-12)
    assert math.isclose(summary["baseline_cooling_year10_min_mw"], 90.0461967, rel_tol=1e-12)
    assert n_plus_one_b >= required_cooling_model(10.0, Q_MAX, T_NORMAL, "B")
    assert math.isclose(RHO * CP * process_b * (T_BOIL - T_NORMAL), required_cooling_model(10.0, Q_MAX, T_TARGET, "B"), rel_tol=1e-12)
    assert (summary["baseline_well_pairs"] - 1) * 1.55 >= process_b
    assert (summary["baseline_well_pairs"] - 1) * 1.55 >= Q_MAX
    assert required_modules(20.0, "B") == 321
    assert (required_modules(20.0, "B") - 1) * 80e6 >= 1.051 * required_cooling_model(20.0, Q_MAX, T_NORMAL, "B")
    full_year20 = (
        required_cooling_model(20.0, Q_MAX, T_NORMAL, "B") / real_cooling_cop()
        + required_cooling_model(20.0, Q_MAX, T_NORMAL, "B") * 0.01 * (1 + 1 / real_cooling_cop())
        + RHO * 9.81 * Q_MAX * 140.0 / 0.75
    )
    assert full_year20 < 7e9
    assert required_modules(10.0, "B") == 160
    assert required_modules(10.0, "A") == 13
    assert math.isclose(growth_a["replacement_meur"], 200 * 17 / 13, rel_tol=1e-12)
    assert math.isclose(growth_b["replacement_meur"], 200 * 229 / 13, rel_tol=1e-12)
    assert annual_b_mean["present_cost_20y_meur"] == stationary_b_mean["present_cost_20y_meur"]
    assert annual_b_low["present_cost_20y_meur"] == stationary_b_low["present_cost_20y_meur"]
    assert annual_b_mean["replacement_meur"] == stationary_b["replacement_meur"]
    assert annual_b_low["replacement_meur"] == stationary_b["replacement_meur"]
    assert annual_a_max["capex_meur"] == 590.0
    assert (summary["baseline_well_pairs"] - 1) * 1.55 >= Q_MAX
    assert math.isclose(sum(CAPEX_BREAKDOWN_MEUR.values()), 500.0)
    assert math.isclose(summary["baseline_exact_installed_threshold_year"], 10.848175090270153, rel_tol=1e-12)
    assert math.isclose(summary["baseline_exact_n_plus_one_threshold_year"], 10.782473660009718, rel_tol=1e-12)
    assert math.isclose(summary["baseline_annual_low"]["annual_electricity_gwh"], 33.47328203696136, rel_tol=1e-12)
    assert all(math.isclose(row["outlet_c"], T_NORMAL) for row in monthly_design(flow=Q_MIN, model="B"))
    assert abs(sum(row["hours"] for row in rows_b) - 8760) == 0
    assert all(row["raw_c"] >= T_BOIL - 1e-9 for row in rows_b)
    assert all(row["heat_removed_mw"] >= row["dry_cooling_mw"] + row["trim_cooling_mw"] - 1e-8 for row in rows_b)
    assert all(row["rejected_mw"] >= row["dry_cooling_mw"] + row["trim_cooling_mw"] for row in rows_b)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    args = parser.parse_args()
    run(args.output_dir)
