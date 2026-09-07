#!/usr/bin/env python3
"""Terminal interface for the smart-irrigation system.

Terminal interaction is kept here. Database, weather, sensor protocol,
irrigation calculations, and pump scheduling use the shared ``core`` package.
"""

import argparse
import json
import math
import os
import signal
import sys
import threading
import time

from core import database, irrigation, sensor, weather


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130


class CliError(RuntimeError):
    """An operational error that can be shown directly to the user."""


class PumpExecutionError(CliError):
    """A pump error with the best available delivery estimate."""

    def __init__(self, message, delivered_liters=0.0, acknowledged=False):
        super().__init__(message)
        self.delivered_liters = max(0.0, float(delivered_liters))
        self.acknowledged = bool(acknowledged)


class PumpExecutionInterrupted(KeyboardInterrupt):
    """An interrupted pump run with the best available delivery estimate."""

    def __init__(self, delivered_liters=0.0, acknowledged=False):
        super().__init__("Pump execution interrupted.")
        self.delivered_liters = max(0.0, float(delivered_liters))
        self.acknowledged = bool(acknowledged)


def parse_soil_values(text):
    """Parse four moisture percentages."""
    try:
        parsed = sensor.parse_sensor_line(str(text))
    except sensor.SerialProtocolError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return tuple(parsed[:4])


def _prompt(input_fn, message, default=None):
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input_fn(f"{message}{suffix}: ").strip()
    if not value and default is not None:
        return str(default)
    return value


def _prompt_float(input_fn, output, message, default, minimum=None, maximum=None):
    while True:
        raw = _prompt(input_fn, message, default)
        try:
            value = float(raw)
        except ValueError:
            output("Value must be numeric.")
            continue
        if not math.isfinite(value):
            output("Value must be finite.")
            continue
        if minimum is not None and value < minimum:
            output(f"Value must be at least {minimum}.")
            continue
        if maximum is not None and value > maximum:
            output(f"Value must not exceed {maximum}.")
            continue
        return value


def _prompt_int(input_fn, output, message, default, minimum=None, maximum=None):
    while True:
        value = _prompt_float(input_fn, output, message, default, minimum, maximum)
        if value.is_integer():
            return int(value)
        output("Value must be an integer.")


class TerminalController:
    """Run validated irrigation cycles without a GUI."""

    def __init__(
        self,
        output=print,
        monotonic=time.monotonic,
        sleeper=time.sleep,
        stop_event=None,
    ):
        self.output = output
        self.monotonic = monotonic
        self.sleeper = sleeper
        self.stop_event = stop_event or threading.Event()

    def initialize(self):
        database.init_database()
        settings = database.db_load_all_settings()
        sensor.configure_serial(
            settings.get("serial_port", "auto"),
            settings.get("baud_rate", 115200),
            reconnect=False,
        )
        irrigation.PUMP_FLOW = list(settings.get("pump_flows", [1.6] * 4))
        weather.WEATHER_REFRESH_HOURS = settings.get("weather_refresh", 1)
        return settings

    def stop(self):
        self.stop_event.set()
        sensor.disable_pump_commands()
        sensor.send_serial_command("SENSOR:STOP")
        sensor.safe_stop_pumps(retries=5, wait_ack=False)
        sensor.set_system_state(sensor.STATE_STOPPED)

    def _load_configuration(
        self,
        plant_name=None,
        location_name=None,
        area=None,
        cultivation_mode=None,
        soil_depth=None,
    ):
        settings = database.db_load_all_settings()
        selected_plant = plant_name or settings.get("active_plant")
        selected_location = location_name or settings.get("active_location")
        plant_row = database.db_get_plant_by_name(selected_plant)
        if not plant_row:
            raise CliError(f"Plant '{selected_plant}' does not exist.")
        location_row = database.db_get_location_by_name(selected_location)
        if not location_row:
            raise CliError("Select or add a valid location before running a cycle.")

        selected_area = float(area if area is not None else settings.get("land_area", 4.0))
        selected_mode = cultivation_mode or settings.get("cultivation_mode", "Field")
        selected_depth = float(
            soil_depth if soil_depth is not None else settings.get("soil_depth", 0.20)
        )
        if not math.isfinite(selected_area) or selected_area <= 0:
            raise CliError("Land area must be finite and positive.")
        if selected_mode not in ("Field", "Container"):
            raise CliError("Cultivation mode must be Field or Container.")
        if not math.isfinite(selected_depth) or not 0.001 <= selected_depth <= 10:
            raise CliError("Soil depth must be between 0.001 and 10 metres.")
        plant = {
            "name": plant_row[1],
            "Kc": plant_row[2],
            "area": selected_area,
            "L": plant_row[3],
            "U": plant_row[4],
        }
        location = {
            "name": location_row[1],
            "lat": location_row[2],
            "lon": location_row[3],
        }
        flows = [float(value) for value in settings.get("pump_flows", [1.6] * 4)]
        if len(flows) != 4 or any(not math.isfinite(value) or value <= 0 for value in flows):
            raise CliError("Four finite, positive pump flow rates are required.")
        return {
            "settings": settings,
            "plant": plant,
            "location": location,
            "cultivation_mode": selected_mode,
            "soil_depth": selected_depth,
            "pump_flows": flows,
        }

    def _collect_hardware_samples(self, duration, minimum_samples, connection_timeout=10.0):
        sensor.start_sensor_reader()
        deadline = self.monotonic() + max(0.1, float(connection_timeout))
        while not sensor.device_verified:
            if self.stop_event.is_set():
                raise CliError("Sensor collection was canceled.")
            if self.monotonic() >= deadline:
                raise CliError("STM32 handshake timed out.")
            self.sleeper(0.1)

        sensor.set_system_state(sensor.STATE_COLLECT)
        sensor.clear_latest_soil_data()
        with sensor.soil_samples_lock:
            sensor.soil_samples.clear()
        if not sensor.send_serial_command("SENSOR:START"):
            raise CliError("Sensor serial link is unavailable.")

        started = self.monotonic()
        try:
            while self.monotonic() - started < duration:
                if self.stop_event.is_set():
                    raise CliError("Sensor collection was canceled.")
                remaining = max(0, int(duration - (self.monotonic() - started)))
                self.output(f"Collecting sensor data: {remaining}s remaining", end="\r")
                self.sleeper(0.2)
        finally:
            sensor.send_serial_command("SENSOR:STOP")
        self.output("")
        with sensor.soil_samples_lock:
            samples = list(sensor.soil_samples)
        return sensor.aggregate_soil_samples(samples, minimum_samples), len(samples)

    @staticmethod
    def _simulated_samples(values, minimum_samples):
        rows = [tuple(values)] * max(1, int(minimum_samples))
        return sensor.aggregate_soil_samples(rows, minimum_samples), len(rows)

    def _get_weather(self, config, force_simulated_weather=False, weather_override=None):
        if weather_override is not None:
            return dict(weather_override)
        location = config["location"]
        settings = config["settings"]
        if force_simulated_weather:
            result = weather.get_simulated_weather(settings.get("simulation_seed", 1))
            result.update({"latitude": location["lat"], "longitude": location["lon"]})
            return result
        return weather.get_weather_cached(
            location["lat"],
            location["lon"],
            allow_simulation=settings.get("allow_simulated_weather", False),
            simulation_seed=settings.get("simulation_seed", 1),
        )

    def _execute_real_schedule(self, schedule, pump_states, pump_flows):
        sensor.enable_pump_commands()
        if not sensor.send_pump_command(*pump_states, wait_ack=True):
            sensor.disable_pump_commands()
            sensor.safe_stop_pumps(retries=5, wait_ack=False)
            raise CliError("Initial pump command was not acknowledged.")

        started = self.monotonic()
        last_states = list(pump_states)
        last_heartbeat = started
        all_acknowledged = True
        execution_error = None
        try:
            while True:
                if sensor.safety_stop_event.is_set():
                    reason = sensor.last_safety_stop_reason or "UNKNOWN"
                    raise CliError(f"Firmware safety stop: {reason}")
                elapsed = self.monotonic() - started
                states = schedule.states_at(elapsed)
                if states != last_states:
                    if not sensor.send_pump_command(*states, wait_ack=True):
                        all_acknowledged = False
                        raise CliError("Pump state change was not acknowledged.")
                    last_states = states
                if not any(states):
                    break
                if self.stop_event.is_set():
                    break
                if self.monotonic() - last_heartbeat >= 5.0:
                    if not sensor.send_heartbeat(wait_ack=True):
                        all_acknowledged = False
                        raise CliError("Pump heartbeat was not acknowledged.")
                    last_heartbeat = self.monotonic()
                remaining = max(0, int(schedule.duration_seconds - elapsed))
                self.output(
                    f"Irrigating: {remaining // 60}:{remaining % 60:02d} remaining; "
                    f"pumps={states}",
                    end="\r",
                )
                self.sleeper(min(0.2, max(0.01, schedule.duration_seconds - elapsed)))
        except (Exception, KeyboardInterrupt) as exc:
            execution_error = exc
            all_acknowledged = False
        finally:
            sensor.disable_pump_commands()
            stopped = sensor.safe_stop_pumps(retries=5, wait_ack=True)
            already_confirmed_off = last_states == [0, 0, 0, 0]
            all_acknowledged = all_acknowledged and (stopped or already_confirmed_off)
            if not stopped and not already_confirmed_off and execution_error is None:
                execution_error = CliError("Final pump stop was not acknowledged.")
            self.output("")

        elapsed = min(self.monotonic() - started, schedule.duration_seconds)
        delivered = schedule.delivered_liters(elapsed, pump_flows)
        if execution_error is not None:
            if isinstance(execution_error, KeyboardInterrupt):
                raise PumpExecutionInterrupted(
                    delivered, all_acknowledged
                ) from execution_error
            raise PumpExecutionError(
                str(execution_error), delivered, all_acknowledged
            ) from execution_error
        status = "stopped" if self.stop_event.is_set() else "completed"
        return delivered, status, all_acknowledged

    def run_cycle(self, **options):
        try:
            return self._run_cycle_impl(**options)
        except KeyboardInterrupt:
            sensor.disable_pump_commands()
            sensor.send_serial_command("SENSOR:STOP")
            sensor.safe_stop_pumps(retries=5, wait_ack=False)
            sensor.set_system_state(sensor.STATE_STOPPED)
            raise
        except Exception:
            sensor.disable_pump_commands()
            sensor.send_serial_command("SENSOR:STOP")
            sensor.safe_stop_pumps(retries=5, wait_ack=False)
            sensor.set_system_state(sensor.STATE_ERROR)
            raise

    def _run_cycle_impl(
        self,
        *,
        simulate_hardware=False,
        simulated_soil=(20.0, 50.0, 50.0, 50.0),
        force_simulated_weather=False,
        weather_override=None,
        plant_name=None,
        location_name=None,
        area=None,
        cultivation_mode=None,
        soil_depth=None,
    ):
        if self.stop_event.is_set():
            raise CliError("Controller is stopped.")
        config = self._load_configuration(
            plant_name, location_name, area, cultivation_mode, soil_depth
        )
        settings = config["settings"]
        plant = config["plant"]
        location = config["location"]
        minimum_samples = max(1, int(settings.get("minimum_samples", 3)))
        sample_started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        sensor.set_system_state(sensor.STATE_COLLECT)
        if simulate_hardware:
            soil, sample_count = self._simulated_samples(simulated_soil, minimum_samples)
        else:
            duration = max(1.0, float(settings.get("collect_duration", 60)))
            soil, sample_count = self._collect_hardware_samples(duration, minimum_samples)

        sensor.set_system_state(sensor.STATE_DECIDE)
        weather_data = self._get_weather(config, force_simulated_weather, weather_override)
        source = weather_data.get("source", "UNKNOWN")
        decision = irrigation.make_decision(
            soil[4],
            plant,
            weather_data,
            config["cultivation_mode"],
            config["soil_depth"],
            soil_values=soil[:4],
            irrigation_efficiency=settings.get("irrigation_efficiency", 0.85),
            soil_water_capacity=settings.get("soil_water_capacity", 0.20),
            rainfall_efficiency=settings.get("rainfall_efficiency", 0.80),
        )
        decision["location_name"] = location["name"]
        decision["pump_flows"] = list(config["pump_flows"])
        pump_states, pump_times = irrigation.zone_irrigation_control(
            soil,
            decision["water_final"],
            plant["L"],
            zone_water_liters=decision["zone_water_liters"],
            max_runtime_minutes=settings.get("max_pump_runtime", 30.0),
            pump_flows=config["pump_flows"],
        )
        sample_meta = {
            "count": sample_count,
            "started_at": sample_started_at,
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        record_id = database.db_save_record(
            decision,
            soil,
            weather_data,
            source,
            location["lat"],
            location["lon"],
            plant["name"],
            config["cultivation_mode"],
            config["soil_depth"],
            sample_meta,
            pump_states,
            pump_times,
        )

        schedule = irrigation.PumpSchedule(tuple(pump_times))
        if not any(pump_states) or schedule.duration_seconds <= 0:
            delivered, status, acknowledged = 0.0, "not_required", True
        elif simulate_hardware:
            delivered = 0.0
            requested_times = [
                liters / flow
                for liters, flow in zip(decision["zone_water_liters"], config["pump_flows"])
            ]
            capped = any(
                requested > actual + 1e-9
                for requested, actual in zip(requested_times, pump_times)
            )
            status = "simulation_only_capped" if capped else "simulation_only"
            acknowledged = False
        else:
            sensor.set_system_state(sensor.STATE_IRRIGATE)
            try:
                delivered, status, acknowledged = self._execute_real_schedule(
                    schedule, pump_states, config["pump_flows"]
                )
                requested_times = [
                    liters / flow
                    for liters, flow in zip(
                        decision["zone_water_liters"], config["pump_flows"]
                    )
                ]
                if status == "completed" and any(
                    requested > actual + 1e-9
                    for requested, actual in zip(requested_times, pump_times)
                ):
                    status = "completed_capped"
            except (Exception, KeyboardInterrupt) as exc:
                database.db_update_irrigation_result(
                    record_id,
                    getattr(exc, "delivered_liters", 0.0),
                    "interrupted" if isinstance(exc, KeyboardInterrupt) else "error",
                    pump_states,
                    pump_times,
                    getattr(exc, "acknowledged", False),
                )
                sensor.set_system_state(sensor.STATE_ERROR)
                raise

        database.db_update_irrigation_result(
            record_id, delivered, status, pump_states, pump_times, acknowledged
        )
        sensor.set_system_state(sensor.STATE_STOPPED)
        result = {
            "record_id": record_id,
            "soil": soil,
            "weather": weather_data,
            "decision": decision,
            "pump_states": pump_states,
            "pump_times": pump_times,
            "delivered_liters": delivered,
            "status": status,
            "pump_acknowledged": acknowledged,
        }
        self._print_cycle_result(result)
        return result

    def run_cycles(self, count=1, interval=None, **cycle_options):
        cycles = int(count)
        if cycles < 1:
            raise CliError("Cycle count must be at least one.")
        results = []
        for index in range(cycles):
            if self.stop_event.is_set():
                break
            self.output(f"\n=== Irrigation cycle {index + 1} of {cycles} ===")
            results.append(self.run_cycle(**cycle_options))
            if index + 1 < cycles:
                wait_seconds = (
                    float(interval)
                    if interval is not None
                    else float(database.db_load_setting("cycle_interval", 300))
                )
                if not math.isfinite(wait_seconds) or wait_seconds < 0:
                    raise CliError("Cycle interval must be finite and non-negative.")
                deadline = self.monotonic() + wait_seconds
                while self.monotonic() < deadline and not self.stop_event.is_set():
                    self.sleeper(min(0.2, deadline - self.monotonic()))
        return results

    def _print_cycle_result(self, result):
        decision = result["decision"]
        self.output(f"Record ID: {result['record_id']}")
        values = ", ".join(f"{value:.1f}%" for value in result["soil"][:4])
        self.output(f"Soil values: {values}")
        self.output(f"Soil median: {result['soil'][4]:.1f}%")
        self.output(f"Weather source: {result['weather'].get('source', 'UNKNOWN')}")
        self.output(f"Planned water: {decision['water_final']:.3f} L")
        self.output(f"Pump states: {result['pump_states']}")
        times = ", ".join(
            irrigation.format_minutes_to_mmss(value) for value in result["pump_times"]
        )
        self.output(f"Pump times: {times}")
        self.output(f"Estimated delivered: {result['delivered_liters']:.3f} L")
        self.output(f"Status: {result['status']}")


class InteractiveTerminal:
    """Menu-based terminal user interface."""

    def __init__(self, controller, input_fn=input, output=print):
        self.controller = controller
        self.input = input_fn
        self.output = output

    def run(self):
        while not self.controller.stop_event.is_set():
            self.output("\nSmart Irrigation CLI")
            self.output("1. Run one irrigation cycle")
            self.output("2. Run repeated irrigation cycles")
            self.output("3. Plant management")
            self.output("4. Location management")
            self.output("5. Settings")
            self.output("6. Weather")
            self.output("7. Irrigation history")
            self.output("0. Exit")
            try:
                choice = _prompt(self.input, "Select", "0")
            except (EOFError, KeyboardInterrupt):
                choice = "0"
            try:
                if choice == "1":
                    self._run_cycles(1)
                elif choice == "2":
                    count = int(_prompt(self.input, "Number of cycles", "2"))
                    self._run_cycles(count)
                elif choice == "3":
                    self._plants_menu()
                elif choice == "4":
                    self._locations_menu()
                elif choice == "5":
                    self._settings_menu()
                elif choice == "6":
                    self._show_weather()
                elif choice == "7":
                    self._show_history()
                elif choice == "0":
                    self.controller.stop()
                else:
                    self.output("Unknown selection.")
            except (CliError, ValueError, OSError, weather.WeatherError) as exc:
                self.output(f"Error: {exc}")
        return EXIT_OK

    def _run_cycles(self, count):
        simulated = _prompt(self.input, "Simulate sensors and pumps? (y/N)", "N").lower() == "y"
        options = {"simulate_hardware": simulated}
        if simulated:
            raw = _prompt(self.input, "Four soil values", "20,50,50,50")
            options["simulated_soil"] = parse_soil_values(raw)
            options["force_simulated_weather"] = (
                _prompt(self.input, "Use simulated weather? (y/N)", "N").lower() == "y"
            )
        else:
            confirmation = _prompt(
                self.input, "Real pumps can operate. Type RUN to continue", "CANCEL"
            )
            if confirmation != "RUN":
                self.output("Cycle canceled.")
                return
        self.controller.run_cycles(count=count, **options)

    def _plants_menu(self):
        plants = database.db_get_all_plants()
        active = database.db_load_setting("active_plant", "")
        for row in plants:
            marker = "*" if row[1] == active else " "
            self.output(f"{marker} {row[1]}: Kc={row[2]:.2f}, L={row[3]:.1f}, U={row[4]:.1f}")
        action = _prompt(self.input, "Action: select/add/edit/delete/back", "back").lower()
        if action == "select":
            name = _prompt(self.input, "Plant name")
            if not database.db_get_plant_by_name(name):
                raise CliError("Plant does not exist.")
            database.db_save_setting("active_plant", name)
        elif action == "add":
            name = _prompt(self.input, "Name")
            kc = _prompt_float(self.input, self.output, "Kc", 1.0, 0.01, 3.0)
            lower = _prompt_float(self.input, self.output, "Lower threshold", 40, 0, 100)
            upper = _prompt_float(self.input, self.output, "Upper threshold", 70, 0, 100)
            if not database.db_add_plant(name, kc, lower, upper):
                raise CliError("Plant already exists.")
        elif action == "edit":
            old_name = _prompt(self.input, "Existing name")
            old = database.db_get_plant_by_name(old_name)
            if not old:
                raise CliError("Plant does not exist.")
            name = _prompt(self.input, "Name", old[1])
            kc = _prompt_float(self.input, self.output, "Kc", old[2], 0.01, 3.0)
            lower = _prompt_float(self.input, self.output, "Lower threshold", old[3], 0, 100)
            upper = _prompt_float(self.input, self.output, "Upper threshold", old[4], 0, 100)
            if not database.db_update_plant(old_name, name, kc, lower, upper):
                raise CliError("Plant could not be updated.")
            if active == old_name:
                database.db_save_setting("active_plant", name)
        elif action == "delete":
            name = _prompt(self.input, "Plant name")
            if name == active:
                raise CliError("Select another plant before deleting the active plant.")
            if not database.db_delete_plant(name):
                raise CliError("Plant does not exist.")

    def _locations_menu(self):
        locations = database.db_get_all_locations()
        active = database.db_load_setting("active_location", "")
        for row in locations:
            marker = "*" if row[1] == active else " "
            self.output(f"{marker} {row[1]}: {row[2]:.6f}, {row[3]:.6f}")
        action = _prompt(self.input, "Action: select/add/edit/delete/back", "back").lower()
        if action == "select":
            name = _prompt(self.input, "Location name")
            if not database.db_get_location_by_name(name):
                raise CliError("Location does not exist.")
            database.db_save_setting("active_location", name)
        elif action == "add":
            name = _prompt(self.input, "Name")
            lat = _prompt_float(self.input, self.output, "Latitude", 0, -90, 90)
            lon = _prompt_float(self.input, self.output, "Longitude", 0, -180, 180)
            if not database.db_add_location(name, lat, lon):
                raise CliError("Location already exists.")
        elif action == "edit":
            old_name = _prompt(self.input, "Existing name")
            old = database.db_get_location_by_name(old_name)
            if not old:
                raise CliError("Location does not exist.")
            name = _prompt(self.input, "Name", old[1])
            lat = _prompt_float(self.input, self.output, "Latitude", old[2], -90, 90)
            lon = _prompt_float(self.input, self.output, "Longitude", old[3], -180, 180)
            if not database.db_update_location(old_name, name, lat, lon):
                raise CliError("Location could not be updated.")
            if active == old_name:
                database.db_save_setting("active_location", name)
        elif action == "delete":
            name = _prompt(self.input, "Location name")
            if name == active:
                raise CliError("Select another location before deleting the active location.")
            if not database.db_delete_location(name):
                raise CliError("Location does not exist.")

    def _settings_menu(self):
        settings = database.db_load_all_settings()
        self.output(json.dumps(settings, indent=2, ensure_ascii=False))
        if _prompt(self.input, "Change common irrigation settings? (y/N)", "N").lower() != "y":
            return
        settings["land_area"] = _prompt_float(
            self.input, self.output, "Land area (m2)", settings["land_area"], 0.000001
        )
        mode = _prompt(
            self.input, "Mode: Field or Container", settings["cultivation_mode"]
        ).title()
        if mode not in ("Field", "Container"):
            raise CliError("Mode must be Field or Container.")
        settings["cultivation_mode"] = mode
        depth_label = "Root-zone depth (m)" if mode == "Field" else "Container soil depth (m)"
        settings["soil_depth"] = _prompt_float(
            self.input, self.output, depth_label, settings["soil_depth"], 0.001, 10
        )
        advanced = _prompt(self.input, "Change advanced control settings? (y/N)", "N").lower()
        if advanced == "y":
            settings["serial_port"] = _prompt(
                self.input, "Serial port or auto", settings["serial_port"]
            )
            settings["baud_rate"] = _prompt_int(
                self.input, self.output, "Baud rate", settings["baud_rate"], 1
            )
            settings["collect_duration"] = _prompt_int(
                self.input, self.output, "Collection duration (s)",
                settings["collect_duration"], 1
            )
            settings["cycle_interval"] = _prompt_int(
                self.input, self.output, "Cycle interval (s)",
                settings["cycle_interval"], 1
            )
            settings["minimum_samples"] = _prompt_int(
                self.input, self.output, "Minimum valid samples",
                settings["minimum_samples"], 1
            )
            expected_samples = int(
                settings["collect_duration"] / sensor.SENSOR_SAMPLE_INTERVAL_SECONDS
            )
            if settings["minimum_samples"] > max(1, expected_samples):
                raise CliError(
                    "Minimum samples exceeds the samples expected during collection."
                )
            settings["weather_refresh"] = _prompt_int(
                self.input, self.output, "Weather refresh (hours)",
                settings["weather_refresh"], 1, 24
            )
            allow_default = "y" if settings["allow_simulated_weather"] else "N"
            settings["allow_simulated_weather"] = (
                _prompt(self.input, "Allow weather fallback simulation? (y/N)", allow_default).lower()
                == "y"
            )
            flow_text = _prompt(
                self.input,
                "Four pump flows in L/min",
                ",".join(str(value) for value in settings["pump_flows"]),
            )
            try:
                flows = [float(value.strip()) for value in flow_text.split(",")]
            except ValueError as exc:
                raise CliError("Pump flows must be numeric.") from exc
            if len(flows) != 4 or any(
                not math.isfinite(value) or value <= 0 for value in flows
            ):
                raise CliError("Four finite, positive pump flows are required.")
            settings["pump_flows"] = flows
            settings["max_pump_runtime"] = _prompt_float(
                self.input, self.output, "Maximum pump runtime (min)",
                settings["max_pump_runtime"], 1.0 / 60.0, 30
            )
            settings["irrigation_efficiency"] = _prompt_float(
                self.input, self.output, "Irrigation efficiency",
                settings["irrigation_efficiency"], 0.01, 1
            )
            settings["soil_water_capacity"] = _prompt_float(
                self.input, self.output, "Calibrated soil water capacity",
                settings["soil_water_capacity"], 0.001, 1
            )
            settings["rainfall_efficiency"] = _prompt_float(
                self.input, self.output, "Effective rain fraction",
                settings["rainfall_efficiency"], 0, 1
            )
            settings["history_retention_days"] = _prompt_int(
                self.input, self.output, "History retention (days)",
                settings["history_retention_days"], 1
            )
        database.db_save_all_settings(settings)
        self.controller.initialize()

    def _show_weather(self):
        config = self.controller._load_configuration()
        simulated = _prompt(self.input, "Force simulated weather? (y/N)", "N").lower() == "y"
        data = self.controller._get_weather(config, simulated)
        self.output(json.dumps(data, indent=2, ensure_ascii=False))

    def _show_history(self, limit=20):
        rows = database.db_get_history(limit)
        if not rows:
            self.output("History is empty.")
            return
        self.output("ID | Timestamp | Plant | Location | Planned L | Delivered L | Status")
        for row in rows:
            self.output(
                f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | "
                f"{float(row[9] or 0):.3f} | {float(row[24] or 0):.3f} | {row[25]}"
            )


def build_parser():
    parser = argparse.ArgumentParser(description="Smart Irrigation terminal application")
    parser.add_argument("--database", help="Use a specific SQLite database file")
    parser.add_argument("--run", action="store_true", help="Run cycles without the menu")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles for --run")
    parser.add_argument("--interval", type=float, help="Seconds between cycles")
    parser.add_argument(
        "--simulate", action="store_true", help="Simulate sensors and pumps; no serial commands"
    )
    parser.add_argument(
        "--simulate-weather", action="store_true", help="Use deterministic simulated weather"
    )
    parser.add_argument(
        "--soil", type=parse_soil_values, default=(20.0, 50.0, 50.0, 50.0)
    )
    parser.add_argument("--plant", help="Plant name override")
    parser.add_argument("--location", help="Location name override")
    parser.add_argument("--area", type=float, help="Land area in square metres")
    parser.add_argument("--mode", choices=("Field", "Container"), help="Cultivation mode")
    parser.add_argument("--depth", type=float, help="Root-zone or container depth in metres")
    parser.add_argument("--yes", action="store_true", help="Confirm real pump operation")
    parser.add_argument("--history", type=int, metavar="N", help="Show latest N records and exit")
    parser.add_argument("--list-plants", action="store_true", help="List plants and exit")
    parser.add_argument("--list-locations", action="store_true", help="List locations and exit")
    return parser


def main(argv=None, input_fn=input, output=print):
    args = build_parser().parse_args(argv)
    if args.database:
        database.DB_FILE = os.path.abspath(args.database)
    controller = TerminalController(output=output)

    previous_sigint = None
    previous_sigterm = None
    handlers_installed = False

    def handle_stop(signum=None, frame=None):
        del signum, frame
        controller.stop()
        raise KeyboardInterrupt

    if threading.current_thread() is threading.main_thread():
        previous_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, handle_stop)
        if hasattr(signal, "SIGTERM"):
            previous_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, handle_stop)
        handlers_installed = True

    try:
        controller.initialize()
        if args.list_plants:
            for row in database.db_get_all_plants():
                output(f"{row[1]} | Kc={row[2]:.2f} | L={row[3]:.1f} | U={row[4]:.1f}")
            return EXIT_OK
        if args.list_locations:
            for row in database.db_get_all_locations():
                output(f"{row[1]} | {row[2]:.6f}, {row[3]:.6f}")
            return EXIT_OK
        if args.history is not None:
            InteractiveTerminal(controller, input_fn, output)._show_history(max(1, args.history))
            return EXIT_OK
        if args.run:
            if not args.simulate and not args.yes:
                raise CliError("Use --yes to confirm real pump operation, or use --simulate.")
            controller.run_cycles(
                count=args.cycles,
                interval=args.interval,
                simulate_hardware=args.simulate,
                simulated_soil=args.soil,
                force_simulated_weather=args.simulate_weather,
                plant_name=args.plant,
                location_name=args.location,
                area=args.area,
                cultivation_mode=args.mode,
                soil_depth=args.depth,
            )
            return EXIT_OK
        return InteractiveTerminal(controller, input_fn, output).run()
    except KeyboardInterrupt:
        controller.stop()
        output("Interrupted.")
        return EXIT_INTERRUPTED
    except Exception as exc:
        controller.stop()
        output(f"Error: {exc}")
        return EXIT_ERROR
    finally:
        if handlers_installed:
            signal.signal(signal.SIGINT, previous_sigint)
            if hasattr(signal, "SIGTERM") and previous_sigterm is not None:
                signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    sys.exit(main())
