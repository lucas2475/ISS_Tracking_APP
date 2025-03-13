import requests
import math
import xmltodict
import logging
import time 
import redis
import json


from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from astropy import coordinates
from astropy import units
from astropy.time import Time
from geopy.geocoders import Nominatim

from flask import Flask, request

app = Flask(__name__)


def get_redis_client():
    """Initialize and return a Redis client."""
    return redis.Redis(host='redis-db', port=6379, db=0, decode_responses=True)

rd = get_redis_client()

URL = "https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml"

def fetch_iss_data():
    """Download ISS data from the webist

        Returns: 
            str:XML data as string
    """
    response = requests.get(URL)
    if response.status_code == 200:
        return response.text

    else:
        print("fail to find the file")
        return None

def parse_iss_data(xml_string):
    """Parses XML string into a Python library
        Arg: xml data as string 

        Returns: XML data as the dictionary format 

    """
    data_dict = xmltodict.parse(xml_string)
    return data_dict


def extract_state_vectors(data_dict):
    """Extract state vectors from parases XML data
       Arg: xml data as dicionary format

       Return: list of state vector dictionaries
    """
    state_vectors = data_dict ["ndm"]["oem"]["body"]["segment"]["data"]["stateVector"]
    return state_vectors

def fetch_and_store_iss_data():
    """
    Fetch ISS data, parse it, and store it in Redis with EPOCH as the key
    """

    if rd.keys():
        return

    xml_string = fetch_iss_data()
    if not xml_string:
        return 
    
    data_dict = parse_iss_data(xml_string)
    state_vectors = extract_state_vectors(data_dict)

    for sv in state_vectors:
        epoch_key = sv["EPOCH"]  
        rd.set(epoch_key, json.dumps(sv))      

    print("ISS data stored successfully in Redis.")


def print_range_data(state_vectors: List[Dict[str,Any]]) -> Dict[str,Any]:
    """print the range of the data

    Arg: list of state vector dictionaries

    """
    first_element = state_vectors[0]["EPOCH"]
    last_element = state_vectors[-1]["EPOCH"]
    
    return first_element, last_element
    
def print_latest_data(state_vectors: List[Dict[str,Any]]) -> Dict[str,Any]:
    """find the data closest to the run time
    Arg: List of sate vector dictionaries

    """
    current_time = datetime.utcnow()
    closest_time = None
    min_diff = float('inf')
    last_element = None

    for sv in state_vectors:
        epoch_str = sv["EPOCH"]
        
        epoch_time = datetime.strptime(epoch_str, "%Y-%jT%H:%M:%S.%fZ")
        
        time_diff = abs((current_time - epoch_time).total_seconds())

        if time_diff < min_diff:
            min_diff = time_diff
            closest_time = epoch_time
            last_element = sv



    return last_element


def calculate_average_speed(state_vectors: List[Dict[str,Any]]) -> float:
    """calculate the average speed of ISS

    Arg: List of state vector dictionaries

    """
    speed = []
    for sv in state_vectors:
        x_dot = float(sv["X_DOT"]["#text"])
        y_dot = float(sv["Y_DOT"]["#text"])
        z_dot = float(sv["Z_DOT"]["#text"])

        speed_update = math.sqrt(x_dot**2 + y_dot**2 + z_dot**2)
        speed.append(speed_update)

    average_speed = sum(speed)/len(speed)
    return average_speed 


def calcualte_instantaneous_speed(state_vectors:List[Dict[str,Any]]) -> float:
    """caculate the instantaneous speed

    Arg: List of state vector dictionaries

    """
    current_time = datetime.utcnow()
    closest_time = None
    min_diff = float('inf')
    last_element = None

    for sv in state_vectors:
        epoch_str = sv["EPOCH"]

        epoch_time = datetime.strptime(epoch_str, "%Y-%jT%H:%M:%S.%fZ")

        time_diff = abs((current_time - epoch_time).total_seconds())

        if time_diff < min_diff:
            min_diff = time_diff
            closest_time = epoch_time
            last_element = sv

    x_dot = float(last_element["X_DOT"]["#text"])
    y_dot = float(last_element["Y_DOT"]["#text"])
    z_dot = float(last_element["Z_DOT"]["#text"])

    
    speed = math.sqrt(x_dot**2 + y_dot**2 + z_dot**2)
    return speed


def to_datetime(epoch: dict):
    """
    Converts the epoch to a datetime object

    Args:
        epoch (dict): state vectors of the ISS for a given epoch

    Returns:
        datetime object of epoch
    """
    return datetime(
        int(epoch["EPOCH"][0:4]), 1, 1
    ) + timedelta(
        days=int(epoch["EPOCH"][5:8]) - 1,
        hours=int(epoch["EPOCH"][9:11]),
        minutes=int(epoch["EPOCH"][12:14]),
        seconds=float(epoch["EPOCH"][15:21]),
    )


def convert_to_lat_lon_alt(epoch: dict):
    """
    Computes the latitude, longitude, and altitude of the ISS given
    coordinates in the J2000 reference frame

    Args:
        epoch (dict): state vectors of the ISS for a given epoch

    Returns:
        latitude, longitude, and altitude of the ISS in km
    """
    date = to_datetime(epoch)
    x = float(epoch["X"]["#text"])
    y = float(epoch["Y"]["#text"])
    z = float(epoch["Z"]["#text"])

    lat = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))
    alt = math.sqrt(x**2 + y**2 + z**2) - 6371.0088
    lon = (math.degrees(math.atan2(y, x)) - ((date.hour - 12) + (date.minute / 60)) * (360 / 24) + 19)

    if lon > 180:
        lon = -180 + (lon - 180)
    if lon < -180:
        lon = 180 + (lon + 180)

    return lat, lon, alt

def get_geolocation(coordinates: str):
    """
    Uses geopy to get the location of ISS

    Args:
        coordinates (string): latitude and longitude

    Returns:
        locaton of the ISS
    """
    geolocator = Nominatim(user_agent="iss_tracker_app")
    location = geolocator.reverse(coordinates, zoom=15, language="en")
    if location is None:
        return "Over the ocean"
    return location.raw["display_name"]




@app.route('/epochs', methods=['GET'])
def epochs():
    """
    Route to return all stored ISS state vectors from Redis.

    Query parameters:
        limit (int): Maximum number of results to return.
        offset (int): Number of results to skip before returning data.
    """
    all_keys = sorted(rd.keys())  
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int, default=0)

    all_keys = all_keys[offset:]

    if limit:
        all_keys = all_keys[:limit]

    state_vectors = [json.loads(rd.get(epoch)) for epoch in all_keys]
    return state_vectors

@app.route('/epochs/<epoch>', methods=['GET'])
def get_epoch(epoch):
    """
    Route to return a specific epoch's state vector from Redis.

    Args:
        epoch (string): specific timestamp of the epoch
    """
    data = rd.get(epoch)  
    if data:
        return json.loads(data)  
    else:
        return {"error": "Epoch not found"}, 404


@app.route('/epochs/<epoch>/speed', methods=['GET'])
def speed(epoch):
    """
    Route to return a specific epoch's speed in the ISS dataset.

    Args:
        epoch (string): specific timestamp of the epoch
    """
    data = rd.get(epoch)  
    if not data:
        return {"error": "Epoch not found"}, 404

    state_vector = json.loads(data)  

    x_dot = float(state_vector["X_DOT"]["#text"])
    y_dot = float(state_vector["Y_DOT"]["#text"])
    z_dot = float(state_vector["Z_DOT"]["#text"])

    speed = math.sqrt(x_dot**2 + y_dot**2 + z_dot**2)  
    return {"epoch": epoch, "speed_km_s": speed}


@app.route('/now', methods=['GET'])
def closest_data():
    """
    Route to return the closest epoch to the current time along with its speed in the ISS dataset.
    """
    all_keys = sorted(rd.keys())  
    if not all_keys:
        return {"error": "No data available"}, 404

    state_vectors = [json.loads(rd.get(epoch)) for epoch in all_keys]
    closest_vector = print_latest_data(state_vectors)

    x_dot = float(closest_vector["X_DOT"]["#text"])
    y_dot = float(closest_vector["Y_DOT"]["#text"])
    z_dot = float(closest_vector["Z_DOT"]["#text"])

    speed = math.sqrt(x_dot**2 + y_dot**2 + z_dot**2)
    lat, lon, alt = convert_to_lat_lon_alt(closest_vector)
    geolocation = get_geolocation(f"{lat}, {lon}")

    return {
        "closest_epoch": closest_vector["EPOCH"],
        "speed_km_s": speed,
        "latitude": lat,
        "longitude": lon,
        "altitude_km": alt,
        "geo_location": geolocation
    }

@app.route('/epochs/<epoch>/location', methods=['GET'])
def get_location(epoch):
    """
    Route to return latitude, longitude, altitude, and geolocation for a specific epoch in the ISS dataset.

    Args:
        epoch (string): specific timestamp of the epoch

    Returns:
        JSON response with latitude, longitude, altitude, and geolocation
    """
    data = rd.get(epoch)  
    if not data:
        return {"error": "Epoch not found"}, 404

    state_vector = json.loads(data)  

 
    lat, lon, alt = convert_to_lat_lon_alt(state_vector)


    geolocation = get_geolocation(f"{lat}, {lon}")

    return {
        "epoch": epoch,
        "latitude": lat,
        "longitude": lon,
        "altitude_km": alt,
        "geolocation": geolocation
    }


if __name__ == "__main__":
    fetch_and_store_iss_data()
    app.run(host='0.0.0.0', port = 5000)
