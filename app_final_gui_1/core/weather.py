import json
import math
import random
import threading
import time
import urllib.parse
import urllib.request


DAYS_FORECAST = 2
WEATHER_REFRESH_HOURS = 1
WEATHER_SOURCE = "NONE"
WEATHER_CACHE = {}
LAST_WEATHER_TIME = 0
_cache_lock = threading.Lock()


class WeatherError(RuntimeError):
    pass


def _finite(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"{name} is not numeric") from exc
    if not math.isfinite(number):
        raise WeatherError(f"{name} is not finite")
    return number


def _coordinates(lat, lon):
    latitude = _finite(lat, "latitude")
    longitude = _finite(lon, "longitude")
    if not -90 <= latitude <= 90:
        raise WeatherError("latitude is outside -90..90")
    if not -180 <= longitude <= 180:
        raise WeatherError("longitude is outside -180..180")
    return latitude, longitude


def get_simulated_weather(seed=None):
    generator = random.Random(seed)
    weather = {"et0": [], "rain": [], "tmin": [], "tmax": []}
    for _ in range(DAYS_FORECAST):
        weather["et0"].append(round(generator.uniform(3, 6), 2))
        weather["rain"].append(round(generator.uniform(0, 5), 2))
        weather["tmin"].append(round(generator.uniform(15, 20), 1))
        weather["tmax"].append(round(generator.uniform(25, 35), 1))
    weather.update({
        "source": "SIMULATED",
        "simulated": True,
        "simulation_seed": seed,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    return weather


def _fetch_json(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "smart-irrigation/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if getattr(response, "status", 200) != 200:
            raise WeatherError(f"weather API returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _validated_daily(payload):
    if not isinstance(payload, dict):
        raise WeatherError("weather response is not an object")
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherError("weather daily data is missing")
    mapping = {
        "et0": "et0_fao_evapotranspiration",
        "rain": "precipitation_sum",
        "tmin": "temperature_2m_min",
        "tmax": "temperature_2m_max",
    }
    result = {}
    for output_key, api_key in mapping.items():
        values = daily.get(api_key)
        if not isinstance(values, list) or len(values) < DAYS_FORECAST:
            raise WeatherError(f"weather field {api_key} has fewer than {DAYS_FORECAST} days")
        result[output_key] = [_finite(value, api_key) for value in values[:DAYS_FORECAST]]
    if any(value < 0 for value in result["et0"]):
        raise WeatherError("weather ET0 cannot be negative")
    if any(value < 0 for value in result["rain"]):
        raise WeatherError("weather precipitation cannot be negative")
    if any(low > high for low, high in zip(result["tmin"], result["tmax"])):
        raise WeatherError("weather minimum temperature exceeds maximum temperature")
    return result


def get_weather(lat, lon, allow_simulation=False, simulation_seed=None, timeout=10):
    global WEATHER_SOURCE
    latitude, longitude = _coordinates(lat, lon)
    query = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "daily": "et0_fao_evapotranspiration,precipitation_sum,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": DAYS_FORECAST,
    })
    url = f"https://api.open-meteo.com/v1/forecast?{query}"
    try:
        weather = _validated_daily(_fetch_json(url, timeout))
        weather.update({
            "source": "API",
            "simulated": False,
            "simulation_seed": None,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "latitude": latitude,
            "longitude": longitude,
        })
        WEATHER_SOURCE = "API"
        return weather
    except Exception as exc:
        if not allow_simulation:
            WEATHER_SOURCE = "ERROR"
            if isinstance(exc, WeatherError):
                raise
            raise WeatherError(f"weather request failed: {exc}") from exc
        weather = get_simulated_weather(seed=simulation_seed)
        weather.update({"latitude": latitude, "longitude": longitude, "fallback_reason": str(exc)})
        WEATHER_SOURCE = "SIMULATED"
        return weather


def _cache_key(lat, lon, allow_simulation, simulation_seed):
    latitude, longitude = _coordinates(lat, lon)
    return (round(latitude, 6), round(longitude, 6), bool(allow_simulation), simulation_seed)


def get_weather_cached(
    lat,
    lon,
    force_refresh=False,
    allow_simulation=False,
    simulation_seed=None,
):
    global LAST_WEATHER_TIME, WEATHER_SOURCE
    key = _cache_key(lat, lon, allow_simulation, simulation_seed)
    refresh_seconds = max(0.0, float(WEATHER_REFRESH_HOURS)) * 3600.0
    now = time.monotonic()
    with _cache_lock:
        entry = WEATHER_CACHE.get(key)
        if not force_refresh and entry and now - entry["monotonic"] <= refresh_seconds:
            WEATHER_SOURCE = entry["weather"].get("source", "NONE")
            return dict(entry["weather"])

    weather = get_weather(
        lat,
        lon,
        allow_simulation=allow_simulation,
        simulation_seed=simulation_seed,
    )
    with _cache_lock:
        WEATHER_CACHE[key] = {"monotonic": time.monotonic(), "weather": dict(weather)}
        LAST_WEATHER_TIME = time.time()
    return weather


def clear_weather_cache():
    global LAST_WEATHER_TIME
    with _cache_lock:
        WEATHER_CACHE.clear()
        LAST_WEATHER_TIME = 0
