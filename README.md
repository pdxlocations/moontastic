# Moontastic

Moontastic is a small Flask app for automated Meshtastic moonbounce-style link testing. It sends numbered test packets through a Meshtastic node, records received packets and acknowledgements, and exposes a simple dashboard plus JSON API.

The app defaults to simulator mode so it can be developed without a radio attached.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
flask --app app run --debug
```

Open `http://127.0.0.1:5000`.

## Configuration

Environment variables:

```bash
MOONTASTIC_INTERFACE=sim        # sim, serial, tcp, or ble
MOONTASTIC_SERIAL_PORT=/dev/ttyUSB0
MOONTASTIC_TCP_HOST=meshtastic.local
MOONTASTIC_BLE_ADDRESS=Meshtastic_1234
MOONTASTIC_DB=moontastic.sqlite3
MOONTASTIC_SECRET=change-me
MOONTASTIC_LAT=45.5152
MOONTASTIC_LON=-122.6784
MOONTASTIC_ELEVATION_M=50
MOONTASTIC_FREQ_MHZ=144
MOONTASTIC_TX_POWER_DBM=30
MOONTASTIC_TX_GAIN_DBI=12
MOONTASTIC_RX_GAIN_DBI=12
MOONTASTIC_RX_SENSITIVITY_DBM=-137
```

For serial hardware:

```bash
MOONTASTIC_INTERFACE=serial MOONTASTIC_SERIAL_PORT=/dev/ttyUSB0 flask --app app run
```

For TCP hardware:

```bash
MOONTASTIC_INTERFACE=tcp MOONTASTIC_TCP_HOST=192.168.1.50 flask --app app run
```

For Bluetooth hardware:

```bash
MOONTASTIC_INTERFACE=ble MOONTASTIC_BLE_ADDRESS=Meshtastic_1234 flask --app app run
```

## API

- `GET /api/status` - current runner and interface status
- `POST /api/connection` - connect using simulator, TCP/IP, serial, or Bluetooth
- `POST /api/connection/disconnect` - close the active interface
- `GET /api/connection/ble/scan` - scan for Meshtastic BLE peripherals
- `GET /api/moon` - live Moon pointing and reception prediction
- `POST /api/tests` - start an automated test
- `POST /api/tests/current/stop` - stop the active test
- `GET /api/tests` - recent tests
- `GET /api/tests/<id>` - test details and packets
- `POST /api/send` - send a one-off text packet

Example test request:

```json
{
  "name": "Night pass",
  "callsign": "N0CALL",
  "target": "!ffffffff",
  "channel": 0,
  "interval_seconds": 30,
  "packet_count": 10,
  "timeout_seconds": 20,
  "payload_prefix": "MOON"
}
```
