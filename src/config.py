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
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
PAUSE_BETWEEN_CITIES_SECONDS = 1

# How many days of hourly data to request (past and future)
PAST_DAYS = 2
FORECAST_DAYS = 2

# 69 Pakistani cities: name -> (latitude, longitude, province)
# The first 20 are the original project cities. The other 49 were added later;
# their coordinates come from the Open-Meteo Geocoding API.
CITIES = {
    # --- Original 20 cities ---
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
    # --- Added: Punjab ---
    "Rahim Yar Khan": (28.4199, 70.3034, "Punjab"),
    "Jhang": (31.2698, 72.3169, "Punjab"),
    "Dera Ghazi Khan": (30.0459, 70.6403, "Punjab"),
    "Gujrat": (32.5742, 74.0754, "Punjab"),
    "Sahiwal": (30.6659, 73.1019, "Punjab"),
    "Wah Cantt": (33.7709, 72.7512, "Punjab"),
    "Kasur": (31.1187, 74.4502, "Punjab"),
    "Okara": (30.8103, 73.4515, "Punjab"),
    "Chiniot": (31.7209, 72.9784, "Punjab"),
    "Kamoke": (31.9753, 74.2230, "Punjab"),
    "Hafizabad": (32.0710, 73.6880, "Punjab"),
    "Burewala": (30.1667, 72.6500, "Punjab"),
    "Khanewal": (30.3017, 71.9321, "Punjab"),
    "Muzaffargarh": (30.0726, 71.1938, "Punjab"),
    "Jhelum": (32.9345, 73.7310, "Punjab"),
    "Mandi Bahauddin": (32.5870, 73.4912, "Punjab"),
    # --- Added: Sindh ---
    "Nawabshah": (26.2394, 68.4037, "Sindh"),
    "Kotri": (25.3657, 68.3083, "Sindh"),
    "Shikarpur": (27.9556, 68.6382, "Sindh"),
    "Jacobabad": (28.2819, 68.4376, "Sindh"),
    "Khairpur": (27.5295, 68.7592, "Sindh"),
    "Dadu": (26.7303, 67.7769, "Sindh"),
    "Badin": (24.6560, 68.8370, "Sindh"),
    "Thatta": (24.7475, 67.9235, "Sindh"),
    "Ghotki": (28.0044, 69.3157, "Sindh"),
    "Sanghar": (26.0469, 68.9492, "Sindh"),
    "Tando Adam": (25.7682, 68.6620, "Sindh"),
    "Tando Allahyar": (25.4605, 68.7174, "Sindh"),
    # --- Added: Khyber Pakhtunkhwa ---
    "Mingora": (34.7795, 72.3627, "Khyber Pakhtunkhwa"),
    "Kohat": (33.5820, 71.4493, "Khyber Pakhtunkhwa"),
    "Dera Ismail Khan": (31.8313, 70.9017, "Khyber Pakhtunkhwa"),
    "Bannu": (32.9853, 70.6040, "Khyber Pakhtunkhwa"),
    "Nowshera": (34.0191, 71.9745, "Khyber Pakhtunkhwa"),
    "Swabi": (34.1202, 72.4698, "Khyber Pakhtunkhwa"),
    "Charsadda": (34.1482, 71.7406, "Khyber Pakhtunkhwa"),
    "Mansehra": (34.3302, 73.1968, "Khyber Pakhtunkhwa"),
    "Haripur": (33.9978, 72.9349, "Khyber Pakhtunkhwa"),
    "Karak": (33.1163, 71.0935, "Khyber Pakhtunkhwa"),
    "Hangu": (33.5320, 71.0595, "Khyber Pakhtunkhwa"),
    # --- Added: Balochistan ---
    "Turbat": (26.0012, 63.0485, "Balochistan"),
    "Khuzdar": (27.8119, 66.6110, "Balochistan"),
    "Hub": (25.0255, 66.8853, "Balochistan"),
    "Sibi": (29.5430, 67.8773, "Balochistan"),
    "Zhob": (31.3408, 69.4493, "Balochistan"),
    "Loralai": (30.3705, 68.5979, "Balochistan"),
    "Chaman": (30.9177, 66.4526, "Balochistan"),
    "Dera Murad Jamali": (28.5466, 68.2231, "Balochistan"),
    "Panjgur": (26.9719, 64.0946, "Balochistan"),
    "Kalat": (29.0266, 66.5936, "Balochistan"),
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