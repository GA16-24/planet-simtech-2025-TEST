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


def required_cooling_temperature_slope(year, flow, target=T_TARGET):
    raw = T0 + (T_BOIL - T0) * year / YEARS_TO_BOIL
    return RHO * CP * flow * max(0.0, raw - target)


def controlled_temperature(year, flow, capacity, target=T_TARGET):
    removed = min(capacity, required_cooling(year, flow, target))
    remaining_heat = heat_input(year) - removed
    return min(T_BOIL, T0 + remaining_heat / (RHO * CP * flow))


def carnot_cooling_cop(t_cold_c=7.0, t_hot_c=45.0):
    return (t_cold_c + 273.15) / (t_hot_c - t_cold_c)


def real_cooling_cop():
    return 0.55 * carnot_cooling_cop()


def required_process_flow(flow, raw, cooled=9.5, target=T_TARGET):
    if raw <= target:
        return 0.0
    return flow * (raw - target) / (raw - cooled)


def monthly_design(flow=Q_MEAN, capacity=None, year=10.0, target=T_NORMAL,
                   approach=10.0, fan_fraction=0.01, head=140.0):
    """Monatsmodell mit Wärmeabfuhr, Kondensatorlast und Hilfsenergie."""
    if capacity is None:
        capacity = 13 * 80e6
    air_temperatures = [0.0, 1.0, 4.0, 8.0, 13.0, 16.0, 18.0, 18.0, 14.0, 9.0, 4.0, 1.0]
    month_hours = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    cop = real_cooling_cop()
    raw = T0 + heat_input(year) / (RHO * CP * flow)
    process_flow = required_process_flow(flow, raw, cooled=target, target=target)
    pump_mw = RHO * 9.81 * process_flow * head / 0.75 / 1e6
    rows = []
    for month, (air, hours) in enumerate(zip(air_temperatures, month_hours), start=1):
        heat = min(capacity, required_cooling(year, flow, target))
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
                     monthly_options=None):
    fixed_eur = 110e6
    modules = 3
    monthly_options = monthly_options or {}
    npv = fixed_eur + modules * module_eur
    schedule = []
    replacement_eur = 0.0
    for year in range(1, 21):
        design_year = min(year, constant_after_year) if constant_after_year else year
        needed = max(3, math.ceil(required_cooling(design_year, Q_MIN) / 80e6) + 1)
        if year >= 10:
            needed = max(13, needed)
        new_modules = max(0, needed - modules)
        modules = max(modules, needed)
        expansion = new_modules * module_eur
        npv += expansion / (1 + discount) ** (year - 1)
        rows = monthly_design(capacity=math.inf, year=design_year, **monthly_options)
        electricity_gwh = sum(row["electric_gwh"] for row in rows)
        maintenance = 0.025 * (fixed_eur + modules * module_eur)
        operating = electricity_gwh * 1000 * electricity_eur_mwh + maintenance
        npv += operating / (1 + discount) ** year
        replacement_eur = 100e6 * modules / 13
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


def write_svg(path, title, x_label, y_label, series, width=900, height=480):
    left, right, top, bottom = 80, 30, 55, 65
    pw, ph = width - left - right, height - top - bottom
    all_points = [point for _, points, _ in series for point in points]
    xmin = min(p[0] for p in all_points)
    xmax = max(p[0] for p in all_points)
    ymin = min(0.0, min(p[1] for p in all_points))
    ymax = max(p[1] for p in all_points)
    if ymax == ymin:
        ymax = ymin + 1

    def sx(x):
        return left + (x - xmin) / (xmax - xmin) * pw

    def sy(y):
        return top + (ymax - y) / (ymax - ymin) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#18242c;font-size:15px}.title{font-size:23px;font-weight:700}.grid{stroke:#dce3e8;stroke-width:1}.axis{stroke:#536570;stroke-width:1.5}</style>',
        f'<text class="title" x="{left}" y="32">{title}</text>',
    ]
    for i in range(6):
        value = ymin + (ymax - ymin) * i / 5
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
    parts.append(f'<text x="20" y="{top+ph/2}" text-anchor="middle" transform="rotate(-90 20 {top+ph/2})">{y_label}</text>')
    for index, (name, points, color) in enumerate(series):
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"/>')
        lx = left + 15 + index * 245
        parts.append(f'<line x1="{lx}" y1="{top+18}" x2="{lx+25}" y2="{top+18}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{lx+32}" y="{top+23}">{name}</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def run(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    design_cooling = required_cooling(10.0, Q_MIN)
    installed_capacity = 13 * 80e6
    n_plus_one_capacity = 12 * 80e6
    rows = monthly_design(capacity=installed_capacity)
    growth = growth_economics()
    stationary = growth_economics(constant_after_year=10)

    with (output_dir / "verlauf.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["jahr", "waerme_mw", "natur_mean_c", "natur_min_c", "natur_max_c", "bedarf_mean_mw", "bedarf_min_mw", "geregelt_1040mw_c", "geregelt_nplus1_960mw_c"])
        for step in range(201):
            year = step / 10
            writer.writerow([
                year, heat_input(year) / 1e6,
                natural_temperature(year, Q_MEAN), natural_temperature(year, Q_MIN),
                natural_temperature(year, Q_MAX), required_cooling(year, Q_MEAN) / 1e6,
                required_cooling(year, Q_MIN) / 1e6,
                controlled_temperature(year, Q_MEAN, installed_capacity),
                controlled_temperature(year, Q_MEAN, n_plus_one_capacity),
            ])

    with (output_dir / "monate.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with (output_dir / "ausbau.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(growth["schedule"][0]))
        writer.writeheader()
        writer.writerows(growth["schedule"])

    years = [step / 10 for step in range(201)]
    write_svg(
        output_dir / "temperaturverlauf.svg",
        "Reale Anlagenreserve bei weiter wachsender Wärme",
        "Zeit in Jahren", "Temperatur in °C",
        [
            ("ohne Eingriff, MQ", [(y, natural_temperature(y, Q_MEAN)) for y in years], "#d1495b"),
            ("1040 MW", [(y, controlled_temperature(y, Q_MEAN, installed_capacity)) for y in years], "#00798c"),
            ("N+1: 960 MW", [(y, controlled_temperature(y, Q_MEAN, n_plus_one_capacity)) for y in years], "#edae49"),
            ("Sollwert", [(y, T_TARGET) for y in years], "#384d48"),
        ],
    )
    write_svg(
        output_dir / "schuettung.svg",
        "Temperatur bis zur Siedegrenze",
        "Zeit in Jahren", "Temperatur in °C",
        [
            ("Minimum", [(y, natural_temperature(y, Q_MIN)) for y in years], "#d1495b"),
            ("Mittel", [(y, natural_temperature(y, Q_MEAN)) for y in years], "#edae49"),
            ("Maximum", [(y, natural_temperature(y, Q_MAX)) for y in years], "#00798c"),
        ],
    )
    write_svg(
        output_dir / "kaelte-monate.svg",
        "Kaskade im zehnten Jahr bei mittlerer Schüttung",
        "Monat", "Leistung in MW",
        [
            ("Trockenkühlung", [(r["month"], r["dry_cooling_mw"]) for r in rows], "#00798c"),
            ("Nachkühlung", [(r["month"], r["trim_cooling_mw"]) for r in rows], "#edae49"),
            ("Strom mit Hilfsenergie", [(r["month"], r["electric_mw"]) for r in rows], "#d1495b"),
        ],
    )

    raw_max = liquid_temperature_before_capping(10.0, Q_MAX)
    process_max = required_process_flow(Q_MAX, raw_max)
    annual_base = economics(rows)
    annual_base["present_cost_20y_meur"] = stationary["present_cost_20y_meur"]
    annual_base["replacement_meur"] = stationary["replacement_meur"]
    annuity = (1 - 1.03 ** -20) / 0.03
    sensitivity = {}
    for name, capex, price in [("low_capex_low_power", 250e6, 80.0), ("high_capex_high_power", 650e6, 200.0)]:
        module_eur = (capex - 110e6) / 13
        annual = economics(rows, capex_eur=capex, electricity_eur_mwh=price)
        annual["present_cost_20y_meur"] = growth_economics(
            electricity_eur_mwh=price, module_eur=module_eur, constant_after_year=10
        )["present_cost_20y_meur"]
        sensitivity[name] = annual
    sensitivity["with_100gwh_heat_sales"] = economics(rows, heat_sales_gwh=100)
    sensitivity["with_100gwh_heat_sales"]["present_cost_20y_meur"] = (
        stationary["present_cost_20y_meur"] - 4.5e6 * annuity / 1e6
    )
    energy_sensitivity = {}
    for name, options in [
        ("approach_5k", {"approach": 5.0}),
        ("approach_12k", {"approach": 12.0}),
        ("fan_2_percent", {"fan_fraction": 0.02}),
        ("head_100m", {"head": 100.0}),
    ]:
        energy_sensitivity[name] = sum(
            row["electric_gwh"] for row in monthly_design(capacity=math.inf, **options)
        )
    summary = {
        "h10_mw": H10 / 1e6,
        "hot_rate_mw_per_year": HOT_RATE / 1e6,
        "cooling_year10_mean_mw": required_cooling(10.0, Q_MEAN) / 1e6,
        "cooling_year10_min_mw": design_cooling / 1e6,
        "cooling_year10_max_mw": required_cooling(10.0, Q_MAX) / 1e6,
        "natural_year10_min_c": natural_temperature(10.0, Q_MIN),
        "natural_year10_max_c": natural_temperature(10.0, Q_MAX),
        "uncapped_year10_min_c": liquid_temperature_before_capping(10.0, Q_MIN),
        "boiling_year_min": boiling_year(Q_MIN),
        "boiling_year_mean": boiling_year(Q_MEAN),
        "boiling_year_max": boiling_year(Q_MAX),
        "temperature_slope_cooling_year10_min_mw": required_cooling_temperature_slope(10.0, Q_MIN) / 1e6,
        "temperature_slope_cooling_year10_mean_mw": required_cooling_temperature_slope(10.0, Q_MEAN) / 1e6,
        "temperature_slope_cooling_year10_max_mw": required_cooling_temperature_slope(10.0, Q_MAX) / 1e6,
        "process_flow_year10_mean_m3s": required_process_flow(Q_MEAN, T_BOIL),
        "process_flow_year10_max_m3s": process_max,
        "bypass_flow_year10_max_m3s": Q_MAX - process_max,
        "well_pairs": 14,
        "flow_per_well_pair_m3s": 1.55,
        "pump_power_year10_max_mw": RHO * 9.81 * process_max * 140.0 / 0.75 / 1e6,
        "well_sensitivity": {
            "low_yield_flow_per_pair_m3s": 0.5,
            "low_yield_pairs_with_reserve": math.ceil(process_max / 0.5) + 1,
            "specific_capacity_l_per_s_m": 15.5,
            "drawdown_m_at_design_yield": 100.0,
            "pressure_rating_bar": 14.0,
            "total_dynamic_head_m": 140.0,
        },
        "year20_raw_mean_c": T0 + heat_input(20.0) / (RHO * CP * Q_MEAN),
        "capex_breakdown_meur": CAPEX_BREAKDOWN_MEUR,
        "installed_modules": 13,
        "module_capacity_mw": 80.0,
        "installed_capacity_mw": installed_capacity / 1e6,
        "capacity_after_one_module_failure_mw": n_plus_one_capacity / 1e6,
        "installed_capacity_threshold_year": next(
            y for y in years if controlled_temperature(y, Q_MIN, installed_capacity) > T_TARGET + 1e-9
        ),
        "n_plus_one_threshold_year": next(
            y for y in years if controlled_temperature(y, Q_MIN, n_plus_one_capacity) > T_TARGET + 1e-9
        ),
        "carnot_cooling_cop": carnot_cooling_cop(),
        "real_cooling_cop": real_cooling_cop(),
        "design_summer_electric_min_mw": design_cooling / real_cooling_cop() / 1e6,
        "economics_base": annual_base,
        "economics_sensitivity": sensitivity,
        "energy_sensitivity_gwh": energy_sensitivity,
        "economics_growth": growth,
        "economics_stationary": stationary,
    }
    (output_dir / "kennwerte.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    assert math.isclose(natural_temperature(10.0, Q_MEAN), T_BOIL, rel_tol=1e-12)
    assert math.isclose(natural_temperature(10.0, Q_MIN), T_BOIL, rel_tol=1e-12)
    assert liquid_temperature_before_capping(10.0, Q_MIN) > 800
    assert math.isclose(boiling_year(Q_MEAN), 10.0, rel_tol=1e-12)
    assert math.isclose(boiling_year(Q_MIN), 1.101321586, rel_tol=1e-8)
    assert math.isclose(boiling_year(Q_MAX), 143.920704846, rel_tol=1e-8)
    assert controlled_temperature(10.0, Q_MIN, design_cooling) <= T_TARGET + 1e-9
    assert math.isclose(RHO * CP * process_max * (raw_max - 9.5), required_cooling(10.0, Q_MAX), rel_tol=1e-12)
    assert 13 * 1.55 >= process_max
    assert math.isclose(sum(CAPEX_BREAKDOWN_MEUR.values()), 500.0)
    assert all(math.isclose(row["outlet_c"], T_NORMAL) for row in monthly_design(flow=Q_MIN))
    assert abs(sum(row["hours"] for row in rows) - 8760) == 0
    assert all(row["raw_c"] >= T_BOIL - 1e-9 for row in rows)
    assert all(row["heat_removed_mw"] >= row["dry_cooling_mw"] + row["trim_cooling_mw"] - 1e-8 for row in rows)
    assert all(row["rejected_mw"] >= row["dry_cooling_mw"] + row["trim_cooling_mw"] for row in rows)
    assert max(row["electric_mw"] for row in rows) < 300.0
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    args = parser.parse_args()
    run(args.output_dir)
