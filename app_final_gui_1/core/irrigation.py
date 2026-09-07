import math
import time
from dataclasses import dataclass


ALGORITHM_VERSION = "2.0"
PUMP_FLOW = [1.6, 1.6, 1.6, 1.6]
ZONE_COUNT = 4
MIN_PUMP_RUNTIME_MINUTES = 1.0 / 60.0
MAX_SAFE_PUMP_RUNTIME_MINUTES = 30.0


class IrrigationInputError(ValueError):
    """Raised when a decision input is missing or physically invalid."""


def _finite_number(value, name, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IrrigationInputError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise IrrigationInputError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise IrrigationInputError(f"{name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise IrrigationInputError(f"{name} must not exceed {maximum}")
    return number


def _weather_values(weather):
    if not isinstance(weather, dict):
        raise IrrigationInputError("weather must be a mapping")
    result = {}
    for key in ("et0", "rain", "tmin", "tmax"):
        values = weather.get(key)
        if not isinstance(values, (list, tuple)) or not values:
            raise IrrigationInputError(f"weather.{key} is missing")
        minimum = 0.0 if key in ("et0", "rain") else -100.0
        maximum = 1000.0 if key == "rain" else 70.0 if key in ("tmin", "tmax") else 50.0
        result[key] = [
            _finite_number(value, f"weather.{key}", minimum, maximum)
            for value in values
        ]
    if any(low > high for low, high in zip(result["tmin"], result["tmax"])):
        raise IrrigationInputError("weather minimum temperature exceeds maximum temperature")
    return result


def _note_for_result(active_zones, before_rain, final, soil_values, upper):
    if not active_zones:
        if min(soil_values) >= upper:
            return "No irrigation needed"
        return "Monitoring"
    if final <= 0:
        return "Irrigation canceled by effective rainfall"
    if final < before_rain - 1e-9:
        return "Irrigation reduced by effective rainfall"
    return "Normal irrigation"


def make_decision(
    soil_median,
    plant,
    weather,
    cultivation_mode="Field",
    soil_depth=0.20,
    soil_values=None,
    irrigation_efficiency=0.85,
    soil_water_capacity=0.20,
    rainfall_efficiency=0.80,
):
    """Calculate a validated, zone-aware irrigation decision."""
    if not isinstance(plant, dict):
        raise IrrigationInputError("plant must be a mapping")

    kc = _finite_number(plant.get("Kc"), "plant.Kc", 0.01, 3.0)
    area = _finite_number(plant.get("area"), "plant.area", 0.000001)
    lower = _finite_number(plant.get("L"), "plant.L", 0.0, 100.0)
    upper = _finite_number(plant.get("U"), "plant.U", 0.0, 100.0)
    if lower >= upper:
        raise IrrigationInputError("plant.L must be lower than plant.U")

    depth = _finite_number(soil_depth, "soil_depth", 0.001, 10.0)
    efficiency = _finite_number(irrigation_efficiency, "irrigation_efficiency", 0.01, 1.0)
    water_capacity = _finite_number(soil_water_capacity, "soil_water_capacity", 0.001, 1.0)
    rain_efficiency = _finite_number(rainfall_efficiency, "rainfall_efficiency", 0.0, 1.0)
    median = _finite_number(soil_median, "soil_median", 0.0, 100.0)

    if soil_values is None:
        values = [median] * ZONE_COUNT
    else:
        if len(soil_values) != ZONE_COUNT:
            raise IrrigationInputError("exactly four soil values are required")
        values = [_finite_number(v, f"soil[{i}]", 0.0, 100.0) for i, v in enumerate(soil_values)]
        ordered_values = sorted(values)
        calculated_median = (ordered_values[1] + ordered_values[2]) / 2.0
        if abs(calculated_median - median) > 1e-6:
            raise IrrigationInputError("soil_median does not match the four soil values")
        median = calculated_median

    w = _weather_values(weather)
    et0_today = w["et0"][0]
    rain_next48 = sum(w["rain"][:2])
    target = (lower + upper) / 2.0
    zone_area = area / ZONE_COUNT
    zone_soil_volume_liters = zone_area * depth * 1000.0
    active_zones = [i for i, value in enumerate(values) if value < lower]

    zone_before_rain = [0.0] * ZONE_COUNT
    zone_water = [0.0] * ZONE_COUNT
    mode = str(cultivation_mode).strip().title()
    if mode not in ("Field", "Container"):
        raise IrrigationInputError("cultivation_mode must be Field or Container")

    for index in active_zones:
        deficit_fraction = max(0.0, target - values[index]) / 100.0
        storage_deficit = deficit_fraction * zone_soil_volume_liters * water_capacity
        crop_demand = et0_today * kc * zone_area
        net_before_rain = storage_deficit + crop_demand
        effective_rain = rain_next48 * rain_efficiency * zone_area
        zone_before_rain[index] = net_before_rain / efficiency
        zone_water[index] = max(0.0, net_before_rain - effective_rain) / efficiency

    before_rain = sum(zone_before_rain)
    final = sum(zone_water)
    water_today = et0_today * kc * area
    note = _note_for_result(active_zones, before_rain, final, values, upper)

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "soil": median,
        "soil_values": values,
        "rain_next48": rain_next48,
        "kc": kc,
        "area": area,
        "water_today": water_today,
        "water_final": final,
        "zone_water_liters": zone_water,
        "active_zones": active_zones,
        "note": note,
        "location_name": "",
        "cultivation_mode": mode,
        "soil_depth": depth,
        "l_threshold": lower,
        "u_threshold": upper,
        "algorithm_version": ALGORITHM_VERSION,
    }


def zone_irrigation_control(
    soil,
    water_final,
    plant_L,
    zone_water_liters=None,
    max_runtime_minutes=30.0,
    pump_flows=None,
):
    if len(soil) < ZONE_COUNT:
        raise IrrigationInputError("soil must contain four sensor values")
    values = [_finite_number(soil[i], f"soil[{i}]", 0.0, 100.0) for i in range(ZONE_COUNT)]
    lower = _finite_number(plant_L, "plant_L", 0.0, 100.0)
    total_water = _finite_number(water_final, "water_final", 0.0)
    requested_max_runtime = _finite_number(
        max_runtime_minutes, "max_runtime_minutes", MIN_PUMP_RUNTIME_MINUTES
    )
    max_runtime = min(requested_max_runtime, MAX_SAFE_PUMP_RUNTIME_MINUTES)

    active = [i for i, value in enumerate(values) if value < lower]
    if total_water <= 0 or not active:
        return [0] * ZONE_COUNT, [0.0] * ZONE_COUNT

    if zone_water_liters is None:
        per_zone = total_water / len(active)
        zone_water = [per_zone if i in active else 0.0 for i in range(ZONE_COUNT)]
    else:
        if len(zone_water_liters) != ZONE_COUNT:
            raise IrrigationInputError("zone_water_liters must contain four values")
        zone_water = [
            _finite_number(value, f"zone_water_liters[{i}]", 0.0) if i in active else 0.0
            for i, value in enumerate(zone_water_liters)
        ]

    pump_states = [0] * ZONE_COUNT
    pump_times = [0.0] * ZONE_COUNT
    flows = PUMP_FLOW if pump_flows is None else pump_flows
    if len(flows) != ZONE_COUNT:
        raise IrrigationInputError("four pump flow rates are required")
    for index, liters in enumerate(zone_water):
        flow = _finite_number(flows[index], f"pump_flows[{index}]", 0.001)
        runtime = liters / flow
        if runtime < MIN_PUMP_RUNTIME_MINUTES:
            continue
        pump_states[index] = 1
        pump_times[index] = min(runtime, max_runtime)
    return pump_states, pump_times


@dataclass(frozen=True)
class PumpSchedule:
    pump_times_minutes: tuple

    def __post_init__(self):
        if len(self.pump_times_minutes) != ZONE_COUNT:
            raise IrrigationInputError("pump schedule requires four durations")
        validated = tuple(
            _finite_number(value, f"pump_time[{index}]", 0.0)
            for index, value in enumerate(self.pump_times_minutes)
        )
        object.__setattr__(self, "pump_times_minutes", validated)

    @property
    def duration_seconds(self):
        return max(self.pump_times_minutes, default=0.0) * 60.0

    def states_at(self, elapsed_seconds):
        elapsed = _finite_number(elapsed_seconds, "elapsed_seconds", 0.0)
        return [
            1 if duration > 0 and elapsed < duration * 60.0 else 0
            for duration in self.pump_times_minutes
        ]

    def delivered_liters(self, elapsed_seconds, flows=None):
        elapsed = _finite_number(elapsed_seconds, "elapsed_seconds", 0.0)
        rates = PUMP_FLOW if flows is None else flows
        if len(rates) != ZONE_COUNT:
            raise IrrigationInputError("four pump flow rates are required")
        total = 0.0
        for index, duration in enumerate(self.pump_times_minutes):
            actual_minutes = min(duration, elapsed / 60.0)
            total += actual_minutes * _finite_number(rates[index], f"flow[{index}]", 0.001)
        return total


def format_minutes_to_mmss(minutes):
    value = _finite_number(minutes, "minutes", 0.0)
    total_seconds = int(round(value * 60.0))
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"
