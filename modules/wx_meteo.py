#import openmeteo_requests # pip install openmeteo-requests
#from retry_requests import retry # pip install retry_requests

import requests
import json
from modules.log import logger
from modules.settings import ERROR_FETCHING_DATA

def get_weather_data(api_url, params):
    response = requests.get(api_url, params=params)
    response.raise_for_status()  # Raise an error for bad status codes
    return response.json()

def get_wx_meteo(lat=0, lon=0, unit=0):
	# set forcast days 1 or 3
	forecastDays = 3

	# Make sure all required weather variables are listed here
	# The order of variables in hourly or daily is important to assign them correctly below
	url = "https://api.open-meteo.com/v1/forecast"
	params = {
		"latitude": {lat},
		"longitude": {lon},
		"daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_hours", "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant"],
		"timezone": "auto",
		"forecast_days": {forecastDays}
	}

	# Unit 0 is imperial, 1 is metric
	if unit == 0:
		params["temperature_unit"] = "fahrenheit"
		params["wind_speed_unit"] = "mph"
		params["precipitation_unit"] = "inch"
		params["distance_unit"] = "mile"
		params["pressure_unit"] = "inHg"

	try:
		# Fetch the weather data
		weather_data = get_weather_data(url, params)
	except Exception as e:
		logger.error(f"Error fetching meteo weather data: {e}")
		return "❌ Gagal mengambil data cuaca. Coba lagi nanti."

	# Check if we got a response
	try:
		# Process location
		logger.debug(f"System: Pulled from Open-Meteo in {weather_data['timezone']} {weather_data['timezone_abbreviation']}")
		
		# Ensure response is defined
		response = weather_data
		
		# Process daily data. The order of variables needs to be the same as requested.
		daily = response['daily']
		daily_weather_code = daily['weather_code']
		daily_temperature_2m_max = daily['temperature_2m_max']
		daily_temperature_2m_min = daily['temperature_2m_min']
		daily_precipitation_hours = daily['precipitation_hours']
		daily_precipitation_probability_max = daily['precipitation_probability_max']
		daily_wind_speed_10m_max = daily['wind_speed_10m_max']
		daily_wind_gusts_10m_max = daily['wind_gusts_10m_max']
		daily_wind_direction_10m_dominant = daily['wind_direction_10m_dominant']
	except Exception as e:
		logger.error(f"Error processing meteo weather data: {e}")
		return "❌ Gagal mengambil data cuaca. Coba lagi nanti."

	# convert wind value to cardinal directions
	for value in daily_wind_direction_10m_dominant:
		if value < 22.5:
			wind_direction = "N"
		elif value < 67.5:
			wind_direction = "NE"
		elif value < 112.5:
			wind_direction = "E"
		elif value < 157.5:
			wind_direction = "SE"
		elif value < 202.5:
			wind_direction = "S"
		elif value < 247.5:
			wind_direction = "SW"
		elif value < 292.5:
			wind_direction = "W"
		elif value < 337.5:
			wind_direction = "NW"
		else:
			wind_direction = "N"

	# create a weather report
	# get area name via reverse geocode
	area_name = ""
	try:
		from geopy.geocoders import Nominatim
		geolocator = Nominatim(user_agent="mesh-bot")
		_loc = geolocator.reverse(f"{lat}, {lon}")
		_addr = _loc.raw.get("address", {})
		_city = _addr.get("city") or _addr.get("town") or _addr.get("regency") or _addr.get("county", "")
		_state = _addr.get("state", "")
		area_name = ", ".join(filter(None, [_city, _state]))
	except Exception:
		pass

	weather_report = ""
	if area_name:
		weather_report += f"\U0001f4cd {area_name}\n"
	for i in range(forecastDays):
		if i == 0:
			day_label = "Hari ini"
		elif i == 1:
			day_label = "Besok"
		else:
			day_label = "Lusa"

		# report weather from WMO Weather interpretation codes (WW)
		code_string = ""
		if daily_weather_code[i] == 0:
			code_string = "Cerah ☀️"
		elif daily_weather_code[i] == 1:
			code_string = "Kebanyakan berawan ⛅"
		elif daily_weather_code[i] == 2:
			code_string = "Agak berawan 🌤️"
		elif daily_weather_code[i] == 3:
			code_string = "Mendung 🌥️"
		elif daily_weather_code[i] == 5:
			code_string = "Berkabut tipis 🌫️"
		elif daily_weather_code[i] == 10:
			code_string = "Berkabut 🌫️"
		elif daily_weather_code[i] == 45:
			code_string = "Kabut tebal 🌫️"
		elif daily_weather_code[i] == 48:
			code_string = "Kabut beku 🌫️"
		elif daily_weather_code[i] == 51:
			code_string = "Gerimis tipis 🌦️"
		elif daily_weather_code[i] == 53:
			code_string = "Gerimis sedang 🌦️"
		elif daily_weather_code[i] == 55:
			code_string = "Gerimis lebat 🌧️"
		elif daily_weather_code[i] == 56:
			code_string = "Gerimis beku tipis"
		elif daily_weather_code[i] == 57:
			code_string = "Gerimis beku sedang"
		elif daily_weather_code[i] == 61:
			code_string = "Hujan ringan 🌧️"
		elif daily_weather_code[i] == 63:
			code_string = "Hujan sedang 🌧️"
		elif daily_weather_code[i] == 65:
			code_string = "Hujan lebat 🌧️"
		elif daily_weather_code[i] == 66:
			code_string = "Hujan es tipis"
		elif daily_weather_code[i] == 67:
			code_string = "Hujan es lebat"
		elif daily_weather_code[i] == 71:
			code_string = "Salju tipis ❄️"
		elif daily_weather_code[i] == 73:
			code_string = "Salju sedang ❄️"
		elif daily_weather_code[i] == 75:
			code_string = "Salju lebat ❄️"
		elif daily_weather_code[i] == 77:
			code_string = "Butiran salju ❄️"
		elif daily_weather_code[i] == 78:
			code_string = "Kristal es"
		elif daily_weather_code[i] == 79:
			code_string = "Pelet es"
		elif daily_weather_code[i] == 80:
			code_string = "Hujan shower ringan 🌦️"
		elif daily_weather_code[i] == 81:
			code_string = "Hujan shower sedang 🌧️"
		elif daily_weather_code[i] == 82:
			code_string = "Hujan shower lebat 🌧️"
		elif daily_weather_code[i] == 85:
			code_string = "Shower salju"
		elif daily_weather_code[i] == 86:
			code_string = "Shower salju lebat"
		elif daily_weather_code[i] == 95:
			code_string = "Badai petir ⛈️"
		elif daily_weather_code[i] == 96:
			code_string = "Hujan es ⛈️"
		elif daily_weather_code[i] == 97:
			code_string = "Badai petir lebat ⛈️"
		elif daily_weather_code[i] == 99:
			code_string = "Hujan es lebat ⛈️"

		# build compact line
		if unit == 0:
			temp_str = f"{int(round(daily_temperature_2m_min[i]))}°F–{int(round(daily_temperature_2m_max[i]))}°F"
		else:
			temp_str = f"{int(round(daily_temperature_2m_min[i]))}°C–{int(round(daily_temperature_2m_max[i]))}°C"

		rain_str = ""
		if daily_precipitation_probability_max[i] > 0:
			rain_str = f" • Hujan {int(daily_precipitation_probability_max[i])}%"

		if daily_wind_speed_10m_max[i] > 0:
			wspd = int(round(daily_wind_speed_10m_max[i]))
			wunit = "mph" if unit == 0 else "kph"
			wind_str = f" • Angin {wspd} {wunit} dari {wind_direction}"
		else:
			wind_str = " • Angin tenang"

		weather_report += f"{day_label}: {code_string} {temp_str}{rain_str}{wind_str}\n"

	return weather_report

def get_flood_openmeteo(lat=0, lon=0):
	# set forcast days 1 or 3
	forecastDays = 3

	# Flood data
	url = "https://flood-api.open-meteo.com/v1/flood"
	params = {
		"latitude": {lat},
		"longitude": {lon},
		"timezone": "auto",
		"daily": "river_discharge",
		"forecast_days": forecastDays
	}

	try:
		# Fetch the flood data
		flood_data = get_weather_data(url, params)
	except Exception as e:
		logger.error(f"Error fetching meteo flood data: {e}")
		return "❌ Gagal mengambil data debit sungai. Coba lagi nanti."
	
	# Check if we got a response
	try:
		# Process location
		logger.debug(f"System: Pulled River FLow Data from Open-Meteo {flood_data['timezone_abbreviation']}")
		
		# Ensure response is defined
		response = flood_data
		
		# Process daily data. The order of variables needs to be the same as requested.
		daily = response['daily']
		daily_river_discharge = daily['river_discharge']
		# check if none

	except Exception as e:
		logger.error(f"Error processing meteo flood data: {e}")
		return "❌ Gagal mengambil data debit sungai. Coba lagi nanti."
	
	if not daily_river_discharge or all(v is None for v in daily_river_discharge):
		return "🌊 Gak ada data sungai di lokasi ini (mungkin jauh dari aliran sungai besar)."

	# create a flood report — one line per forecast day, flagged if discharge
	# is trending up sharply (naive proxy for rising flood risk)
	day_labels = ["Hari ini", "Besok", "Lusa"]
	lines = ["🌊 Debit Sungai Terdekat"]
	prev = None
	for i, discharge in enumerate(daily_river_discharge):
		label = day_labels[i] if i < len(day_labels) else f"+{i}d"
		if discharge is None:
			continue
		flag = ""
		if prev is not None and prev > 0 and discharge > prev * 1.3:
			flag = " ⚠️ naik tajam"
		lines.append(f"{label}: {discharge:.1f} m3/s{flag}")
		prev = discharge
	lines.append("📡 open-meteo.com (flood-api)")

	return "\n".join(lines)
