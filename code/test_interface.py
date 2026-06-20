# -*- coding: utf-8 -*-
"""
Temporary interface test for member 2's generate_adsb_frame(state).

Purpose: probe the REAL contract of member 2's framing function before wiring
it into transmitter.py, and document any deviation from the task's recommended
state shape / return type. This script does NOT modify member 2's code.

Run:
    python code/test_interface.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adsb_frame import (  # noqa: E402
    generate_adsb_frame,
    bits_to_string,
    parse_frame_fields,
    string_to_bits,
)


# Task-recommended state (member-2 INCOMPATIBLE -> kept only for documentation)
RECOMMENDED_STATE = {
    "icao": "ABCDEF",
    "callsign": "TEST123",
    "altitude": 8000,
    "speed": 230,
    "heading": 85,
    "latitude_q": 12345,
    "longitude_q": 54321,
}

# Adapted state matching member 2's REAL required fields
ADAPTED_STATE = {
    "df": 17,
    "ca": 5,
    "icao": 0xABCDEF,        # 24-bit int, not hex string
    "type_code": 19,         # required by member 2 (0-31)
    "altitude": 8000,        # ft, 0-102375
    "speed": 230,            # knots, 0-1023
    "heading": 85.0,         # degrees float [0,360)
    "latitude": 39.9042,     # physical degrees [-90,90], not quantized
    "longitude": 116.4074,   # physical degrees [-180,180], not quantized
}


def _hr(title):
    print("\n" + title)
    print("-" * len(title))


def main():
    ok = True

    # 1) Importability
    _hr("[1] import check")
    print("generate_adsb_frame imported OK:", callable(generate_adsb_frame))

    # 2) Recommended state vs member 2 (document the incompatibility)
    _hr("[2] recommended-state compatibility (expected to be rejected)")
    try:
        generate_adsb_frame(RECOMMENDED_STATE)
        print("WARNING: recommended state was accepted unexpectedly.")
    except Exception as exc:  # noqa: BLE001
        print("recommended state rejected as expected:", repr(exc))
        print("=> transmitter.generate_virtual_aircraft_state() must adapt the fields.")

    # 3) Call with the adapted (member-2 compatible) state
    _hr("[3] call with adapted state")
    frame = generate_adsb_frame(ADAPTED_STATE)
    print("call succeeded, raw return type:", type(frame).__name__)

    # 4) Return shape checks
    _hr("[4] return-shape checks")
    checks = [
        ("is list", isinstance(frame, list)),
        ("length == 112", len(frame) == 112),
        ("content only 0/1", all(b in (0, 1) for b in frame)),
    ]
    for name, result in checks:
        print(f"  {name}: {'PASS' if result else 'FAIL'}")
        ok = ok and result

    # 5) String view (task expected a string; member 2 returns a list of ints,
    #    but provides bits_to_string() -> adapter converts in transmitter.py)
    _hr("[5] string-form check (via member 2 bits_to_string)")
    frame_str = bits_to_string(frame)
    print("string form length:", len(frame_str))
    print("string form only '0'/'1':", all(c in "01" for c in frame_str))
    print("string value:", frame_str)
    ok = ok and (len(frame_str) == 112 and all(c in "01" for c in frame_str))

    # 6) CRC round-trip via member 2's own parser/validator
    _hr("[6] CRC round-trip via member 2 parse_frame_fields")
    parsed = parse_frame_fields(string_to_bits(frame_str))
    crc_ok = bool(parsed["crc_ok"])
    print("crc_ok:", crc_ok)
    print("  parsed df=%s ca=%s icao=%s type_code=%s" % (
        parsed["df"], parsed["ca"], hex(parsed["icao"]), parsed["type_code"]))
    if not crc_ok:
        print("  crc_received  :", parsed["crc_received"])
        print("  crc_calculated:", parsed["crc_calculated"])
    ok = ok and crc_ok

    # 7) Field-name mapping summary
    _hr("[7] field-name mapping (recommended -> member 2 actual)")
    mapping = [
        ("icao",          "ABCDEF (str)",      "0xABCDEF (24-bit int)"),
        ("callsign",      "TEST123",           "(not used by member 2)"),
        ("altitude",      "8000",              "altitude: ft, 0-102375"),
        ("speed",         "230",               "speed: knots, 0-1023"),
        ("heading",       "85",                "heading: float deg [0,360)"),
        ("latitude_q",    "12345 (quantized)", "latitude: physical deg [-90,90]"),
        ("longitude_q",   "54321 (quantized)", "longitude: physical deg [-180,180]"),
        ("(none)",        "-",                 "type_code: required int 0-31"),
        ("(none)",        "-",                 "df (default 17), ca (default 5)"),
    ]
    for a, rec, act in mapping:
        print(f"  {a:<12} recommended={rec:<20} member2={act}")

    print("\nRESULT:", "ALL CORE CHECKS PASS" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
