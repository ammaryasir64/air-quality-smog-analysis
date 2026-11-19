"""
config.py

Central settings for the Air Quality & Smog Analysis project.

Data source: OpenWeather Air Pollution API (needs an API key)
https://openweathermap.org/api/air-pollution

IMPORTANT: The air-quality values are MODEL-BASED ESTIMATES (OpenWeather uses the
SILAM atmospheric model). They are NOT direct measurements from ground
monitoring stations.

The API key is never written in code. It is read from the environment variable
OPENWEATHER_API_KEY (.env locally, GitHub Secrets in Actions).
"""

API_BASE_URL = "https://api.openweathermap.org/data/2.5/air_pollution"
API_KEY_ENV_VAR = "OPENWEATHER_API_KEY"
TIMEZONE = "Asia/Karachi"  # API times are UTC; we convert them to this zone

# Request settings
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
PAUSE_BETWEEN_CALLS_SECONDS = 1.2  # free plan allows 60 calls per minute

# Days of history requested by each regular ETL run (the forecast is added automatically)
HISTORY_DAYS = 2
MAX_HISTORY_DAYS = 30

# 36 major Pakistani cities: name -> (latitude, longitude, province)
# The first 20 are the original project cities. The other 16 are large cities
# that are not right next to another city in the list; their coordinates come
# from a geocoding service.
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
    "Sahiwal": (30.6659, 73.1019, "Punjab"),
    "Okara": (30.8103, 73.4515, "Punjab"),
    "Gujrat": (32.5742, 74.0754, "Punjab"),
    # --- Added: Sindh ---
    "Nawabshah": (26.2394, 68.4037, "Sindh"),
    "Jacobabad": (28.2819, 68.4376, "Sindh"),
    "Dadu": (26.7303, 67.7769, "Sindh"),
    # --- Added: Khyber Pakhtunkhwa ---
    "Mingora": (34.7795, 72.3627, "Khyber Pakhtunkhwa"),
    "Kohat": (33.5820, 71.4493, "Khyber Pakhtunkhwa"),
    "Dera Ismail Khan": (31.8313, 70.9017, "Khyber Pakhtunkhwa"),
    "Bannu": (32.9853, 70.6040, "Khyber Pakhtunkhwa"),
    # --- Added: Balochistan ---
    "Turbat": (26.0012, 63.0485, "Balochistan"),
    "Khuzdar": (27.8119, 66.6110, "Balochistan"),
    "Zhob": (31.3408, 69.4493, "Balochistan"),
}

# The six pollutants used in this project: API name -> column name (all in ug/m3).
# The API also returns NO and NH3; they are deliberately not used.
POLLUTANTS = {
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "co": "carbon_monoxide",
    "so2": "sulphur_dioxide",
    "no2": "nitrogen_dioxide",
    "o3": "ozone",
}
POLLUTANT_COLUMNS = list(POLLUTANTS.values())
CONCENTRATION_UNIT = "µg/m³"