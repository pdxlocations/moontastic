import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_path: str
    interface_type: str
    serial_port: str | None
    tcp_host: str | None
    ble_address: str | None
    secret_key: str
    station_latitude: float
    station_longitude: float
    station_elevation_m: float
    frequency_mhz: float
    tx_power_dbm: float
    tx_gain_dbi: float
    rx_gain_dbi: float
    rx_sensitivity_dbm: float


def load_config() -> Config:
    return Config(
        database_path=os.environ.get("MOONTASTIC_DB", "moontastic.sqlite3"),
        interface_type=os.environ.get("MOONTASTIC_INTERFACE", "sim").lower(),
        serial_port=os.environ.get("MOONTASTIC_SERIAL_PORT"),
        tcp_host=os.environ.get("MOONTASTIC_TCP_HOST"),
        ble_address=os.environ.get("MOONTASTIC_BLE_ADDRESS"),
        secret_key=os.environ.get("MOONTASTIC_SECRET", "dev-secret"),
        station_latitude=float(os.environ.get("MOONTASTIC_LAT", "45.5152")),
        station_longitude=float(os.environ.get("MOONTASTIC_LON", "-122.6784")),
        station_elevation_m=float(os.environ.get("MOONTASTIC_ELEVATION_M", "50")),
        frequency_mhz=float(os.environ.get("MOONTASTIC_FREQ_MHZ", "144")),
        tx_power_dbm=float(os.environ.get("MOONTASTIC_TX_POWER_DBM", "30")),
        tx_gain_dbi=float(os.environ.get("MOONTASTIC_TX_GAIN_DBI", "12")),
        rx_gain_dbi=float(os.environ.get("MOONTASTIC_RX_GAIN_DBI", "12")),
        rx_sensitivity_dbm=float(os.environ.get("MOONTASTIC_RX_SENSITIVITY_DBM", "-137")),
    )
