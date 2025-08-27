import requests

def get_weather_forecast(lat: float, lon: float) -> dict:
    """Get the weather forecast for a location."""
    lat_lng = f"latitude={lat}&longitude={lon}"
    url = f"https://api.open-meteo.com/v1/forecast?{lat_lng}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
    response = requests.get(url)
    json = response.json()
    return json["current"]
