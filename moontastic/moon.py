from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


LIGHT_KM_S = 299792.458
MOON_REFLECTION_LOSS_DB = 120.0


@dataclass(frozen=True)
class Station:
    latitude: float
    longitude: float
    elevation_m: float = 0.0


@dataclass(frozen=True)
class LinkBudget:
    frequency_mhz: float = 144.0
    tx_power_dbm: float = 30.0
    tx_gain_dbi: float = 12.0
    rx_gain_dbi: float = 12.0
    rx_sensitivity_dbm: float = -137.0
    system_loss_db: float = 3.0


def moon_prediction(station: Station, link: LinkBudget, now: datetime | None = None) -> dict[str, Any]:
    instant = normalize_time(now)
    track = moon_topocentric(station, instant)
    link_result = predict_link(track, link)
    return {
        "generated_at": instant.isoformat(timespec="seconds"),
        "station": {
            "latitude": station.latitude,
            "longitude": station.longitude,
            "elevation_m": station.elevation_m,
        },
        "moon": track,
        "link": link_result,
        "window": visible_window(station, instant),
    }


def normalize_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def moon_topocentric(station: Station, when: datetime) -> dict[str, float | str | bool]:
    jd = julian_day(when)
    d = jd - 2451543.5
    n = wrap_degrees(125.1228 - 0.0529538083 * d)
    inc = 5.1454
    arg_perigee = wrap_degrees(318.0634 + 0.1643573223 * d)
    semi_major_axis_earth_radii = 60.2666
    eccentricity = 0.0549
    mean_anomaly = wrap_degrees(115.3654 + 13.0649929509 * d)

    eccentric_anomaly = solve_kepler(math.radians(mean_anomaly), eccentricity)
    xv = semi_major_axis_earth_radii * (math.cos(eccentric_anomaly) - eccentricity)
    yv = semi_major_axis_earth_radii * math.sqrt(1 - eccentricity * eccentricity) * math.sin(eccentric_anomaly)
    true_anomaly = math.degrees(math.atan2(yv, xv))
    distance_earth_radii = math.sqrt(xv * xv + yv * yv)

    xh = distance_earth_radii * (
        cosd(n) * cosd(true_anomaly + arg_perigee)
        - sind(n) * sind(true_anomaly + arg_perigee) * cosd(inc)
    )
    yh = distance_earth_radii * (
        sind(n) * cosd(true_anomaly + arg_perigee)
        + cosd(n) * sind(true_anomaly + arg_perigee) * cosd(inc)
    )
    zh = distance_earth_radii * sind(true_anomaly + arg_perigee) * sind(inc)

    obliquity = 23.4393 - 3.563e-7 * d
    xe = xh
    ye = yh * cosd(obliquity) - zh * sind(obliquity)
    ze = yh * sind(obliquity) + zh * cosd(obliquity)

    ra = math.atan2(ye, xe)
    dec = math.atan2(ze, math.sqrt(xe * xe + ye * ye))
    gmst = greenwich_sidereal_degrees(jd)
    lst = math.radians(wrap_degrees(gmst + station.longitude))
    hour_angle = wrap_radians(lst - ra)

    lat = math.radians(station.latitude)
    altitude = math.asin(
        math.sin(lat) * math.sin(dec)
        + math.cos(lat) * math.cos(dec) * math.cos(hour_angle)
    )
    azimuth = math.atan2(
        -math.sin(hour_angle),
        math.tan(dec) * math.cos(lat) - math.sin(lat) * math.cos(hour_angle),
    )

    distance_km = distance_earth_radii * 6378.14
    previous = moon_range_km(station, when - timedelta(minutes=5))
    next_range = moon_range_km(station, when + timedelta(minutes=5))
    radial_velocity_km_s = (next_range - previous) / 600.0

    phase = lunar_phase(jd)
    return {
        "azimuth_deg": round(wrap_degrees(math.degrees(azimuth)), 2),
        "elevation_deg": round(math.degrees(altitude), 2),
        "range_km": round(distance_km, 0),
        "round_trip_ms": round((2 * distance_km / LIGHT_KM_S) * 1000, 1),
        "radial_velocity_km_s": round(radial_velocity_km_s, 4),
        "round_trip_path_km": round(2 * distance_km, 0),
        "phase_fraction": round(phase["fraction"], 3),
        "phase_age_days": phase["age_days"],
        "phase_name": phase["name"],
        "visible": altitude > 0,
    }


def moon_range_km(station: Station, when: datetime) -> float:
    jd = julian_day(when)
    d = jd - 2451543.5
    mean_anomaly = wrap_degrees(115.3654 + 13.0649929509 * d)
    eccentricity = 0.0549
    eccentric_anomaly = solve_kepler(math.radians(mean_anomaly), eccentricity)
    xv = 60.2666 * (math.cos(eccentric_anomaly) - eccentricity)
    yv = 60.2666 * math.sqrt(1 - eccentricity * eccentricity) * math.sin(eccentric_anomaly)
    return math.sqrt(xv * xv + yv * yv) * 6378.14


def predict_link(track: dict[str, Any], link: LinkBudget) -> dict[str, Any]:
    frequency_hz = link.frequency_mhz * 1_000_000
    range_km = float(track["range_km"])
    wavelength_m = 299792458 / frequency_hz
    one_way_fspl = 32.44 + 20 * math.log10(range_km) + 20 * math.log10(link.frequency_mhz)
    two_way_fspl = 2 * one_way_fspl
    total_loss = (2 * one_way_fspl) + MOON_REFLECTION_LOSS_DB + link.system_loss_db
    eirp_dbm = link.tx_power_dbm + link.tx_gain_dbi
    eirp_w = 10 ** ((eirp_dbm - 30) / 10)
    predicted_rx = link.tx_power_dbm + link.tx_gain_dbi + link.rx_gain_dbi - total_loss
    doppler_hz = -2 * float(track["radial_velocity_km_s"]) * 1000 / 299792458 * frequency_hz
    elevation = float(track["elevation_deg"])
    elevation_penalty = 0 if elevation >= 20 else max(0, 20 - max(elevation, 0)) * 0.8
    margin = predicted_rx - link.rx_sensitivity_dbm - elevation_penalty
    required_combined_gain = link.rx_sensitivity_dbm + total_loss + elevation_penalty - link.tx_power_dbm
    score = max(0, min(100, round((margin + 30) * 2)))

    if elevation <= 0:
        verdict = "Moon below horizon"
        score = 0
    elif margin >= 10:
        verdict = "Favorable"
    elif margin >= 0:
        verdict = "Marginal"
    else:
        verdict = "Unlikely"

    return {
        "frequency_mhz": link.frequency_mhz,
        "wavelength_m": round(wavelength_m, 3),
        "tx_power_dbm": link.tx_power_dbm,
        "tx_power_w": round(10 ** ((link.tx_power_dbm - 30) / 10), 3),
        "tx_gain_dbi": link.tx_gain_dbi,
        "rx_gain_dbi": link.rx_gain_dbi,
        "combined_antenna_gain_dbi": round(link.tx_gain_dbi + link.rx_gain_dbi, 1),
        "eirp_dbm": round(eirp_dbm, 1),
        "eirp_w": round(eirp_w, 3),
        "one_way_fspl_db": round(one_way_fspl, 1),
        "two_way_fspl_db": round(two_way_fspl, 1),
        "reflection_loss_db": MOON_REFLECTION_LOSS_DB,
        "system_loss_db": link.system_loss_db,
        "moonbounce_loss_db": round(total_loss, 1),
        "elevation_penalty_db": round(elevation_penalty, 1),
        "predicted_rx_dbm": round(predicted_rx, 1),
        "rx_sensitivity_dbm": link.rx_sensitivity_dbm,
        "margin_db": round(margin, 1),
        "doppler_hz": round(doppler_hz, 1),
        "required_combined_gain_for_0db_margin_dbi": round(required_combined_gain, 1),
        "required_combined_gain_for_10db_margin_dbi": round(required_combined_gain + 10, 1),
        "score": score,
        "verdict": verdict,
        "assumption": "Approximate passive lunar reflection budget; validate with measured packet results.",
    }


def visible_window(station: Station, start: datetime) -> dict[str, Any]:
    samples = []
    best = None
    rise = None
    setting = None
    was_visible = moon_topocentric(station, start)["visible"]

    for step in range(0, 25 * 4):
        at = start + timedelta(minutes=15 * step)
        track = moon_topocentric(station, at)
        sample = {
            "at": at.isoformat(timespec="minutes"),
            "azimuth_deg": track["azimuth_deg"],
            "elevation_deg": track["elevation_deg"],
            "visible": track["visible"],
        }
        samples.append(sample)
        if best is None or track["elevation_deg"] > best["elevation_deg"]:
            best = sample
        if track["visible"] and not was_visible and rise is None:
            rise = sample["at"]
        if was_visible and not track["visible"] and setting is None:
            setting = sample["at"]
        was_visible = bool(track["visible"])

    return {
        "next_rise": rise,
        "next_set": setting,
        "best": best,
        "best_in_hours": round((datetime.fromisoformat(best["at"]) - start).total_seconds() / 3600, 2) if best else None,
        "samples": samples[::2],
    }


def lunar_phase(jd: float) -> dict[str, Any]:
    synodic_month = 29.530588853
    age = (jd - 2451550.1) % synodic_month
    fraction = 0.5 * (1 - math.cos(2 * math.pi * age / synodic_month))
    names = [
        (1.84566, "New"),
        (5.53699, "Waxing crescent"),
        (9.22831, "First quarter"),
        (12.91963, "Waxing gibbous"),
        (16.61096, "Full"),
        (20.30228, "Waning gibbous"),
        (23.99361, "Last quarter"),
        (27.68493, "Waning crescent"),
        (29.53059, "New"),
    ]
    for limit, name in names:
        if age < limit:
            return {"age_days": round(age, 1), "fraction": fraction, "name": name}
    return {"age_days": round(age, 1), "fraction": fraction, "name": "New"}


def julian_day(when: datetime) -> float:
    when = normalize_time(when)
    year = when.year
    month = when.month
    day = when.day + (
        when.hour + (when.minute + (when.second + when.microsecond / 1_000_000) / 60) / 60
    ) / 24
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5


def greenwich_sidereal_degrees(jd: float) -> float:
    t = (jd - 2451545.0) / 36525
    return wrap_degrees(280.46061837 + 360.98564736629 * (jd - 2451545) + 0.000387933 * t * t - t * t * t / 38710000)


def solve_kepler(mean_anomaly: float, eccentricity: float) -> float:
    eccentric_anomaly = mean_anomaly
    for _ in range(8):
        eccentric_anomaly -= (
            eccentric_anomaly - eccentricity * math.sin(eccentric_anomaly) - mean_anomaly
        ) / (1 - eccentricity * math.cos(eccentric_anomaly))
    return eccentric_anomaly


def wrap_degrees(value: float) -> float:
    return value % 360.0


def wrap_radians(value: float) -> float:
    while value < -math.pi:
        value += 2 * math.pi
    while value > math.pi:
        value -= 2 * math.pi
    return value


def sind(value: float) -> float:
    return math.sin(math.radians(value))


def cosd(value: float) -> float:
    return math.cos(math.radians(value))
