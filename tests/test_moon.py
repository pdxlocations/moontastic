from datetime import datetime, timezone

from moontastic.moon import LinkBudget, Station, moon_prediction, reception_probability_map


def test_moon_prediction_has_tracking_and_link_fields():
    prediction = moon_prediction(
        Station(latitude=45.5152, longitude=-122.6784),
        LinkBudget(),
        datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert -90 <= prediction["moon"]["elevation_deg"] <= 90
    assert 0 <= prediction["moon"]["azimuth_deg"] < 360
    assert prediction["moon"]["range_km"] > 350000
    assert prediction["moon"]["round_trip_ms"] > 2000
    assert prediction["moon"]["round_trip_path_km"] > 700000
    assert "verdict" in prediction["link"]
    assert prediction["link"]["frequency_mhz"] == 144.0
    assert prediction["link"]["wavelength_m"] > 2
    assert "two_way_fspl_db" in prediction["link"]
    assert "required_combined_gain_for_0db_margin_dbi" in prediction["link"]
    assert 0 <= prediction["link"]["score"] <= 100
    assert prediction["window"]["best"]
    assert prediction["window"]["samples"]


def test_link_margin_improves_with_more_antenna_gain():
    station = Station(latitude=45.5152, longitude=-122.6784)
    when = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    base = moon_prediction(station, LinkBudget(tx_gain_dbi=0, rx_gain_dbi=0), when)
    improved = moon_prediction(station, LinkBudget(tx_gain_dbi=20, rx_gain_dbi=20), when)

    assert improved["link"]["margin_db"] > base["link"]["margin_db"]


def test_reception_probability_map_returns_bounded_grid():
    result = reception_probability_map(
        Station(latitude=45.5152, longitude=-122.6784),
        LinkBudget(tx_gain_dbi=20, rx_gain_dbi=20),
        datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
        step_degrees=20,
    )

    assert result["grid_step_degrees"] == 20
    assert result["points"]
    assert 0 <= result["coverage_percent"] <= 100
    assert "moon_visible" in result["tx"]
    assert all(0 <= point["probability"] <= 1 for point in result["points"])
    assert all(point["probability"] == 0 for point in result["points"] if not point["visible"])
