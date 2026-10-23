import requests

def get_weather(city: str = "Hyderabad") -> dict:
    if not city or not city.strip():
        city = "Hyderabad"
    city = city.strip()
    url = f"https://wttr.in/{city}?format=j1"
    headers = {"User-Agent": "JarvisBot/1.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        
        current = data["current_condition"][0]
        weather_desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        feels_like = current["FeelsLikeC"]
        humidity = current["humidity"]
        wind_speed = current["windspeedKmph"]

        # Forecast
        forecast = []
        for day in data.get("weather", [])[:3]:
            forecast.append({
                "date": day.get("date"),
                "max_temp": day.get("maxtempC"),
                "min_temp": day.get("mintempC"),
                "chance_of_rain": day.get("hourly", [{}])[4].get("chanceofrain", "0") + "%"
            })

        return {
            "city": city,
            "condition": weather_desc,
            "temp_c": f"{temp_c}°C",
            "feels_like": f"{feels_like}°C",
            "humidity": f"{humidity}%",
            "wind": f"{wind_speed} km/h",
            "forecast": forecast
        }
    except Exception as e:
        return {"error": f"Failed to retrieve weather for '{city}': {e}"}
