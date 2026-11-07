"""
config.py

Central settings for the Air Quality & Smog Analysis project.

Data source: Open-Meteo Air Quality API
https://air-quality-api.open-meteo.com/v1/air-quality

IMPORTANT: Open-Meteo air-quality values are MODEL-BASED ESTIMATES
(from the CAMS atmospheric model). They are NOT direct measurements
from ground monitoring stations.
"""

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEZONE = "Asia/Karachi"

# Request settings
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
PAUSE_BETWEEN_CITIES_SECONDS = 1

# How many days of hourly data to request (past and future)
PAST_DAYS = 2
FORECAST_DAYS = 2

# 20 Pakistani cities: name -> (latitude, longitude, province)
CITIES = {
    "Lahore": (31.5204, 74.3587, "Punjab"),
    "Rawalpindi": (33.5651, 73.0169, "Punjab"),
    "Faisalabad": (31.4504, 73.1350, "Punjab"),
    "Multan": (30.1575, 71.5249, "Punjab"),
    "Gujranwala": (32.1877, 74.1945, "Punjab"),
    "Sialkot": (32.4945, 74.5229, "Punjab"),
    "Bahawalpur": (29.3956, 71.6836, "Punjab"),
    "Sargodha": (32.0836, 72.6711, "Punjab"),
    "Sheikhupura": (31.7167, 73.9850, "Punjab"),
    "Karachi": (24.8607, 67.0011, "Sindh"),
    "Hyderabad": (25.3960, 68.3578, "Sindh"),
    "Sukkur": (27.7052, 68.8574, "Sindh"),
    "Larkana": (27.5590, 68.2123, "Sindh"),
    "Peshawar": (34.0151, 71.5249, "Khyber Pakhtunkhwa"),
    "Mardan": (34.1989, 72.0231, "Khyber Pakhtunkhwa"),
    "Abbottabad": (34.1688, 73.2215, "Khyber Pakhtunkhwa"),
    "Quetta": (30.1798, 66.9750, "Balochistan"),
    "Gwadar": (25.1216, 62.3254, "Balochistan"),
    "Islamabad": (33.6844, 73.0479, "Islamabad Capital Territory"),
    "Muzaffarabad": (34.3700, 73.4711, "Azad Kashmir"),
}

# Pollutant variables requested from the API (API name -> column name)
POLLUTANTS = {
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "carbon_monoxide": "carbon_monoxide",
    "sulphur_dioxide": "sulphur_dioxide",
    "nitrogen_dioxide": "nitrogen_dioxide",
    "ozone": "ozone",
}

# AQI variables requested from the API
AQI_FIELDS = ["us_aqi", "european_aqi"]

# Full list of variables used for the API request
HOURLY_VARIABLES = list(POLLUTANTS.keys()) + AQI_FIELDS
CURRENT_VARIABLES = list(POLLUTANTS.keys()) + AQI_FIELDS