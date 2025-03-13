import pytest
import requests
import math
import xmltodict
import logging
import time

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from iss_tracker import (
    parse_iss_data,
    extract_state_vectors,
    calculate_average_speed,
    calcualte_instantaneous_speed,
    print_range_data,
    print_latest_data,
    convert_to_lat_lon_alt,
    to_datetime,
    get_geolocation
)

URL = "https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml"


sample_state_vectors = [
    {"EPOCH": "2025-050T12:00:00.000Z",
     "X_DOT": {"text": "1.0"},
     "Y_DOT": {"text": "2.0"},
     "Z_DOT": {"text": "3.0"}},
    {"EPOCH": "2025-051T12:00:00.000Z",
     "X_DOT": {"text": "1.5"},
     "Y_DOT": {"text": "2.5"},
     "Z_DOT": {"text": "3.5"}},
    {"EPOCH": "2025-052T12:00:00.000Z",
     "X_DOT": {"text": "2.0"},
     "Y_DOT": {"text": "3.0"},
     "Z_DOT": {"text": "4.0"}}
]







def fetch_live_iss_data():
    """Fetch real ISS data from NASA API."""
    response = requests.get(URL)
    if response.status_code == 200:
        return response.text
    else:
        pytest.skip("Skipping test: Unable to fetch real ISS data.")

def test_parse_iss_data():
    """Test XML parsing with real data"""
    xml_string = fetch_live_iss_data()
    parsed_data = parse_iss_data(xml_string)
    assert "ndm" in parsed_data
    assert "stateVector" in parsed_data["ndm"]["oem"]["body"]["segment"]["data"]


def test_print_range_data():
    """Test print_range_data function with normal data"""
    first, last = print_range_data(sample_state_vectors)
    assert first == "2025-050T12:00:00.000Z"
    assert last == "2025-052T12:00:00.000Z"

def test_print_latest_data_empty():
    """Test print_latest_data with empty list"""
    latest_data = print_latest_data([])
    assert latest_data is None




def test_extract_state_vectors():
    """Test extracting state vectors with real data"""
    xml_string = fetch_live_iss_data()
    parsed_data = parse_iss_data(xml_string)
    state_vectors = extract_state_vectors(parsed_data)

    assert isinstance(state_vectors, list)  
    assert len(state_vectors) > 0  
    assert "EPOCH" in state_vectors[0]  

def test_calculate_average_speed():
    """Test average speed calculation with real data"""
    xml_string = fetch_live_iss_data()
    parsed_data = parse_iss_data(xml_string)
    state_vectors = extract_state_vectors(parsed_data)

    speed = calculate_average_speed(state_vectors)
    assert speed is not None, "Error: Function returned None"
    assert speed > 0  

def test_calculate_instantaneous_speed():
    """Test instantaneous speed calculation with real data"""
    xml_string = fetch_live_iss_data()
    parsed_data = parse_iss_data(xml_string)
    state_vectors = extract_state_vectors(parsed_data)

    assert calcualte_instantaneous_speed(state_vectors) > 0 


def test_convert_to_lat_lon_alt():
    epoch = {
        "EPOCH": "2024-075T23:01:00.000Z",
        "X": {"#text": "1000"},
        "Y": {"#text": "1000"},
        "Z": {"#text": "1000"}
    }
    expected_lat = 35.264389682754654
    expected_lon = -101.25
    expected_alt = math.sqrt(3*(1000**2)) - 6371.0088

    lat, lon, alt = convert_to_lat_lon_alt(epoch)
    assert expected_lat == lat
    assert expected_lon ==  lon
    assert expected_alt == alt

def test_to_datetime():
    epoch = {
        "EPOCH": "2024-075T23:01:00.000Z"
    }

    expected_datetime = datetime.datetime(2024, 3, 15, 23, 1, 0)

    result_datetime = to_datetime(epoch)

    assert result_datetime == expected_datetime

def test_get_geolocation():
    coordinates = "40.73061, -73.935242"

    result_location = get_geolocation(coordinates)
    assert result_location == "Blissville Yard, Blissville, Queens County, New York, 11222, United States"


