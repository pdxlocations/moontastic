from moontastic.runner import annotate_packet_latencies, summarize_packets


def test_rx_latency_is_derived_from_matching_tx_sequence():
    packets = [
        {
            "direction": "tx",
            "sequence": 7,
            "created_at": "2026-06-15T12:00:00.100+00:00",
            "snr": None,
            "rssi": None,
        },
        {
            "direction": "rx",
            "sequence": 7,
            "created_at": "2026-06-15T12:00:01.350+00:00",
            "snr": 8.5,
            "rssi": -90,
        },
    ]

    annotated = annotate_packet_latencies(packets)
    summary = summarize_packets(annotated)

    assert annotated[0]["latency_ms"] is None
    assert annotated[1]["latency_ms"] == 1250.0
    assert summary["avg_latency_ms"] == 1250.0
    assert summary["min_latency_ms"] == 1250.0
    assert summary["max_latency_ms"] == 1250.0
