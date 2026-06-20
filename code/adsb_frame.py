# -*- coding: utf-8 -*-
"""
ADS-B 1090ES Baseband Communication Prototype System - Protocol Layer (Member 2)
Author: Yin (Part_2_Yin)
Date: 2026-06-14
Description: This module implements the encoding and decoding of the 112-bit
             ADS-B Mode-S Extended Squitter frame, including field quantization,
             56-bit ME field generation/parsing, and Mode-S CRC-24 calculation.
"""

MODE_S_POLY = 0xFFF409

def int_to_bits(value, width):
    """
    Converts an integer to a list of bits (0s and 1s) of a specified width (MSB-first).
    """
    if not isinstance(value, int):
        raise TypeError("value must be int")
    if value < 0 or value >= (1 << width):
        raise ValueError(f"value {value} out of range for {width} bits")
    return [int(x) for x in f"{value:0{width}b}"]

def bits_to_int(bits):
    """
    Converts a list of bits (0s and 1s) to an integer.
    """
    if not bits or any(bit not in (0, 1) for bit in bits):
        raise ValueError("bits must be a non-empty list of 0 or 1")
    return int("".join(map(str, bits)), 2)

def bits_to_string(bits):
    """
    Converts a list of bits to a string of '0' and '1'.
    """
    if not isinstance(bits, list) or any(bit not in (0, 1) for bit in bits):
        raise ValueError("bits must be a list of 0 and 1")
    return "".join(map(str, bits))

def string_to_bits(s):
    """
    Converts a string of '0' and '1' to a list of bits.
    """
    if not isinstance(s, str) or any(c not in ('0', '1') for c in s):
        raise ValueError("string must contain only '0' and '1'")
    return [int(c) for c in s]

def encode_aircraft_state(state):
    """
    Validates and quantizes flight state dictionary.
    Returns: quantized fields dictionary.
    """
    # 1. Check required fields
    required_fields = ["type_code", "altitude", "speed", "heading", "latitude", "longitude"]
    for field in required_fields:
        if field not in state:
            raise ValueError(f"Missing required field: {field}")

    # 2. Check and quantize Type Code (5 bits)
    type_code = state["type_code"]
    if not isinstance(type_code, int) or not (0 <= type_code <= 31):
        raise ValueError("type_code must be an integer between 0 and 31")

    # 3. Check and quantize Altitude (12 bits: 0 to 102375 ft)
    altitude = state["altitude"]
    if not isinstance(altitude, (int, float)) or not (0 <= altitude <= 102375):
        raise ValueError("altitude must be between 0 and 102375 ft")
    altitude_q = int(round(altitude / 25))
    if not (0 <= altitude_q <= 4095):
        raise ValueError("Quantized altitude out of 12-bit range")

    # 4. Check and quantize Speed (10 bits: 0 to 1023 knots)
    speed = state["speed"]
    if not isinstance(speed, (int, float)) or not (0 <= speed <= 1023):
        raise ValueError("speed must be between 0 and 1023 knots")
    speed_q = int(round(speed))
    if not (0 <= speed_q <= 1023):
        raise ValueError("Quantized speed out of 10-bit range")

    # 5. Check and quantize Heading (9 bits: 0 <= heading < 360)
    heading = state["heading"]
    if not isinstance(heading, (int, float)) or not (0.0 <= heading < 360.0):
        raise ValueError("heading must be in range [0.0, 360.0)")
    # Heading is circular: use all 512 codes and wrap values near 360° to code 0.
    heading_q = int(round(heading / 360.0 * 512)) % 512
    if not (0 <= heading_q <= 511):
        raise ValueError("Quantized heading out of 9-bit range")

    # 6. Check and quantize Latitude (10 bits: -90 to 90)
    latitude = state["latitude"]
    if not isinstance(latitude, (int, float)) or not (-90.0 <= latitude <= 90.0):
        raise ValueError("latitude must be in range [-90.0, 90.0]")
    latitude_q = int(round((latitude + 90.0) / 180.0 * 1023))
    if not (0 <= latitude_q <= 1023):
        raise ValueError("Quantized latitude out of 10-bit range")

    # 7. Check and quantize Longitude (10 bits: -180 to 180)
    longitude = state["longitude"]
    if not isinstance(longitude, (int, float)) or not (-180.0 <= longitude <= 180.0):
        raise ValueError("longitude must be in range [-180.0, 180.0]")
    longitude_q = int(round((longitude + 180.0) / 360.0 * 1023))
    if not (0 <= longitude_q <= 1023):
        raise ValueError("Quantized longitude out of 10-bit range")

    return {
        "type_code": type_code,
        "altitude": altitude_q,
        "speed": speed_q,
        "heading": heading_q,
        "latitude": latitude_q,
        "longitude": longitude_q
    }

def decode_aircraft_state(me_bits):
    """
    Decodes the 56-bit ME field into de-quantized physical values.
    """
    if not isinstance(me_bits, list) or len(me_bits) != 56 or any(bit not in (0, 1) for bit in me_bits):
        raise ValueError("me_bits must be a list of 56 bits (0 or 1)")

    type_code_bits = me_bits[0:5]
    altitude_bits = me_bits[5:17]
    speed_bits = me_bits[17:27]
    heading_bits = me_bits[27:36]
    latitude_bits = me_bits[36:46]
    longitude_bits = me_bits[46:56]

    type_code = bits_to_int(type_code_bits)
    altitude_q = bits_to_int(altitude_bits)
    speed_q = bits_to_int(speed_bits)
    heading_q = bits_to_int(heading_bits)
    latitude_q = bits_to_int(latitude_bits)
    longitude_q = bits_to_int(longitude_bits)

    # De-quantize fields
    altitude = int(altitude_q * 25)
    speed = int(speed_q)
    heading = round(heading_q / 512.0 * 360.0, 2)
    latitude = round(latitude_q / 1023.0 * 180.0 - 90.0, 2)
    longitude = round(longitude_q / 1023.0 * 360.0 - 180.0, 2)

    return {
        "type_code": type_code,
        "altitude": altitude,
        "speed": speed,
        "heading": heading,
        "latitude": latitude,
        "longitude": longitude
    }

def generate_me_field(state):
    """
    Generates the 56-bit ME field bits.
    """
    q = encode_aircraft_state(state)

    tc_bits = int_to_bits(q["type_code"], 5)
    alt_bits = int_to_bits(q["altitude"], 12)
    spd_bits = int_to_bits(q["speed"], 10)
    hd_bits = int_to_bits(q["heading"], 9)
    lat_bits = int_to_bits(q["latitude"], 10)
    lon_bits = int_to_bits(q["longitude"], 10)

    me_bits = tc_bits + alt_bits + spd_bits + hd_bits + lat_bits + lon_bits
    if len(me_bits) != 56:
        raise RuntimeError("Internal error: ME field must be exactly 56 bits")
    return me_bits

def generate_crc24(bits):
    """
    Generates 24-bit Mode-S CRC for the 88-bit payload.
    """
    if len(bits) != 88:
        raise ValueError("CRC input must be exactly 88 bits")
    work = bits_to_int(bits) << 24
    for bit_pos in range(111, 23, -1):
        if work & (1 << bit_pos):
            work ^= MODE_S_POLY << (bit_pos - 24)
    return int_to_bits(work & 0xFFFFFF, 24)

def generate_adsb_frame(state):
    """
    Generates complete 112-bit ADS-B frame.
    """
    # Check that state dictionary has df and ca. If not, default them.
    df = state.get("df", 17)
    ca = state.get("ca", 5)
    icao = state["icao"]

    if not isinstance(df, int) or not (0 <= df <= 31):
        raise ValueError("df must be between 0 and 31")
    if not isinstance(ca, int) or not (0 <= ca <= 7):
        raise ValueError("ca must be between 0 and 7")
    if not isinstance(icao, int) or not (0 <= icao <= 0xFFFFFF):
        raise ValueError("icao must be a 24-bit integer")

    df_bits = int_to_bits(df, 5)
    ca_bits = int_to_bits(ca, 3)
    icao_bits = int_to_bits(icao, 24)
    me_bits = generate_me_field(state)

    payload = df_bits + ca_bits + icao_bits + me_bits
    if len(payload) != 88:
        raise RuntimeError("Internal error: ADS-B payload must be exactly 88 bits")

    crc_bits = generate_crc24(payload)
    frame = payload + crc_bits
    if len(frame) != 112:
        raise RuntimeError("Internal error: ADS-B frame must be exactly 112 bits")
    return frame

def parse_frame_fields(bits):
    """
    Parses a 112-bit frame and validates the CRC.
    Returns: decoded fields and CRC check results.
    """
    if not isinstance(bits, list) or len(bits) != 112 or any(bit not in (0, 1) for bit in bits):
        raise ValueError("Frame bits must be a list of exactly 112 bits (0 or 1)")

    payload = bits[0:88]
    crc_received_bits = bits[88:112]

    crc_calculated_bits = generate_crc24(payload)

    # Check CRC
    crc_ok = (crc_received_bits == crc_calculated_bits)

    # Slice payload fields
    df_bits = payload[0:5]
    ca_bits = payload[5:8]
    icao_bits = payload[8:32]
    me_bits = payload[32:88]

    df = bits_to_int(df_bits)
    ca = bits_to_int(ca_bits)
    icao = bits_to_int(icao_bits)

    me_decoded = decode_aircraft_state(me_bits)

    result = {
        "df": df,
        "ca": ca,
        "icao": icao,
        "type_code": me_decoded["type_code"],
        "altitude": me_decoded["altitude"],
        "speed": me_decoded["speed"],
        "heading": me_decoded["heading"],
        "latitude": me_decoded["latitude"],
        "longitude": me_decoded["longitude"],
        "crc_received": bits_to_string(crc_received_bits),
        "crc_calculated": bits_to_string(crc_calculated_bits),
        "crc_ok": crc_ok
    }
    return result

if __name__ == "__main__":
    # Standard test state to verify functionality when run directly
    TEST_STATE = {
        "df": 17,
        "ca": 5,
        "icao": 0xABCDEF,
        "type_code": 19,
        "altitude": 30000,
        "speed": 450,
        "heading": 90.0,
        "latitude": 39.9042,
        "longitude": 116.4074,
    }
    frame = generate_adsb_frame(TEST_STATE)
    print("Generated 112-bit frame:")
    print(bits_to_string(frame))

    parsed = parse_frame_fields(frame)
    print("Parsed result:")
    for k, v in parsed.items():
        if k in ["icao"]:
            print(f"  {k}: {hex(v)}")
        else:
            print(f"  {k}: {v}")
