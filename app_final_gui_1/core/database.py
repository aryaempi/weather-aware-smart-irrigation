import csv
import copy
import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager


DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "irrigation_system.db")
SCHEMA_VERSION = 2
_last_prune_monotonic = 0.0

DEFAULT_PLANTS = [
    {"name": "Wheat", "Kc": 1.15, "L": 45, "U": 70},
    {"name": "Corn", "Kc": 1.20, "L": 40, "U": 65},
    {"name": "Tomato", "Kc": 1.15, "L": 45, "U": 75},
    {"name": "Potato", "Kc": 1.10, "L": 45, "U": 70},
    {"name": "Cucumber", "Kc": 1.05, "L": 40, "U": 70},
    {"name": "Pepper", "Kc": 1.05, "L": 45, "U": 70},
    {"name": "Lettuce", "Kc": 0.95, "L": 40, "U": 65},
    {"name": "Onion", "Kc": 1.05, "L": 40, "U": 65},
    {"name": "Garlic", "Kc": 0.90, "L": 40, "U": 60},
    {"name": "Rice", "Kc": 1.20, "L": 50, "U": 80},
    {"name": "Cotton", "Kc": 1.15, "L": 45, "U": 70},
    {"name": "Sunflower", "Kc": 1.10, "L": 40, "U": 65},
    {"name": "Soybean", "Kc": 1.10, "L": 45, "U": 70},
    {"name": "Alfalfa", "Kc": 1.20, "L": 45, "U": 75},
    {"name": "Grape", "Kc": 0.85, "L": 35, "U": 60},
    {"name": "Apple", "Kc": 0.95, "L": 40, "U": 65},
    {"name": "Orange", "Kc": 0.90, "L": 40, "U": 65},
    {"name": "Lemon", "Kc": 0.90, "L": 40, "U": 65},
    {"name": "Strawberry", "Kc": 0.85, "L": 40, "U": 65},
    {"name": "Carrot", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Pea", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Bean", "Kc": 1.05, "L": 40, "U": 65},
    {"name": "Melon", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Pumpkin", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Eggplant", "Kc": 1.05, "L": 40, "U": 65},
    {"name": "Cabbage", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Broccoli", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Cauliflower", "Kc": 1.00, "L": 40, "U": 65},
    {"name": "Spinach", "Kc": 0.95, "L": 35, "U": 60},
    {"name": "Sugarcane", "Kc": 1.25, "L": 45, "U": 75},
]

DEFAULT_SETTINGS = {
    "serial_port": "auto",
    "baud_rate": 115200,
    "collect_duration": 60,
    "cycle_interval": 300,
    "minimum_samples": 3,
    "weather_refresh": 1,
    "allow_simulated_weather": False,
    "simulation_seed": 1,
    "pump_flows": [1.6, 1.6, 1.6, 1.6],
    "max_pump_runtime": 30.0,
    "irrigation_efficiency": 0.85,
    "soil_water_capacity": 0.20,
    "rainfall_efficiency": 0.80,
    "dark_mode": False,
    "language": "English",
    "active_plant": "Wheat",
    "active_location": "",
    "land_area": 4.0,
    "cultivation_mode": "Field",
    "soil_depth": 0.20,
    "history_retention_days": 365,
}

HISTORY_COLUMNS = """
    id, timestamp, plant_name, location_name, soil_median, kc, area, soil_depth,
    water_needed_liters, water_final_liters, decision_note,
    s1, s2, s3, s4, et0_today, rain_today, rain_next48,
    temp_min, temp_max, weather_source, latitude, longitude, cultivation_mode,
    water_delivered_estimate_liters, irrigation_status, pump_states, pump_times,
    pump_acknowledged, algorithm_version, l_threshold, u_threshold, pump_flows,
    sample_count, weather_payload, sample_started_at, sample_ended_at
"""


def _validated_setting(key, value):
    if key not in DEFAULT_SETTINGS:
        return value
    if key in ("serial_port", "active_plant", "active_location"):
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        if key == "serial_port" and not value.strip():
            raise ValueError("serial_port cannot be empty")
        return value
    if key == "language":
        if value != "English":
            raise ValueError("only English is installed")
        return value
    if key == "cultivation_mode":
        if value not in ("Field", "Container"):
            raise ValueError("invalid cultivation mode")
        return value
    if key in ("allow_simulated_weather", "dark_mode"):
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean")
        return value
    if key == "pump_flows":
        if not isinstance(value, list) or len(value) != 4:
            raise ValueError("pump_flows must contain four values")
        flows = [float(item) for item in value]
        if any(not math.isfinite(item) or item <= 0 for item in flows):
            raise ValueError("pump flow rates must be finite and positive")
        return flows

    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    ranges = {
        "baud_rate": (1, None),
        "collect_duration": (1, None),
        "cycle_interval": (1, None),
        "minimum_samples": (1, None),
        "weather_refresh": (0, 24),
        "simulation_seed": (None, None),
        "max_pump_runtime": (1.0 / 60.0, 30),
        "irrigation_efficiency": (0.01, 1),
        "soil_water_capacity": (0.001, 1),
        "rainfall_efficiency": (0, 1),
        "land_area": (0.000001, None),
        "soil_depth": (0.001, 10),
        "history_retention_days": (1, None),
    }
    minimum, maximum = ranges[key]
    if minimum is not None and number < minimum:
        raise ValueError(f"{key} is below its minimum")
    if maximum is not None and number > maximum:
        raise ValueError(f"{key} exceeds its maximum")
    if key in (
        "baud_rate", "collect_duration", "cycle_interval", "minimum_samples",
        "weather_refresh", "simulation_seed", "history_retention_days",
    ):
        if not number.is_integer():
            raise ValueError(f"{key} must be an integer")
        return int(number)
    return number


@contextmanager
def _connect(path=None, readonly=False):
    filename = path or DB_FILE
    if readonly:
        con = sqlite3.connect(f"file:{filename}?mode=ro", uri=True, timeout=30)
    else:
        con = sqlite3.connect(filename, timeout=30)
    con.execute("PRAGMA busy_timeout = 30000")
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        if not readonly:
            con.commit()
    except Exception:
        if not readonly:
            con.rollback()
        raise
    finally:
        con.close()


def _columns(cur, table):
    return {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}


def _ensure_column(cur, table, name, declaration):
    if name not in _columns(cur, table):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def init_database():
    with _connect() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = FULL")
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS irrigation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                plant_name TEXT NOT NULL DEFAULT '',
                s1 REAL, s2 REAL, s3 REAL, s4 REAL, soil_median REAL,
                et0_today REAL, rain_today REAL, rain_next48 REAL,
                temp_min REAL, temp_max REAL,
                kc REAL, area REAL, soil_depth REAL NOT NULL DEFAULT 0.20,
                water_needed_liters REAL, water_final_liters REAL,
                decision_note TEXT, weather_source TEXT,
                location_name TEXT, latitude REAL, longitude REAL,
                cultivation_mode TEXT NOT NULL DEFAULT 'Field'
            )
        """)
        migrations = {
            "plant_name": "TEXT NOT NULL DEFAULT ''",
            "soil_depth": "REAL NOT NULL DEFAULT 0.20",
            "cultivation_mode": "TEXT NOT NULL DEFAULT 'Field'",
            "water_delivered_estimate_liters": "REAL NOT NULL DEFAULT 0",
            "irrigation_status": "TEXT NOT NULL DEFAULT 'legacy'",
            "pump_states": "TEXT NOT NULL DEFAULT '[]'",
            "pump_times": "TEXT NOT NULL DEFAULT '[]'",
            "pump_acknowledged": "INTEGER NOT NULL DEFAULT 0",
            "algorithm_version": "TEXT NOT NULL DEFAULT 'legacy'",
            "l_threshold": "REAL",
            "u_threshold": "REAL",
            "pump_flows": "TEXT NOT NULL DEFAULT '[]'",
            "sample_count": "INTEGER NOT NULL DEFAULT 0",
            "sample_started_at": "TEXT",
            "sample_ended_at": "TEXT",
            "weather_payload": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, declaration in migrations.items():
            _ensure_column(cur, "irrigation_records", name, declaration)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                kc REAL NOT NULL CHECK(kc > 0),
                l_threshold REAL NOT NULL CHECK(l_threshold >= 0 AND l_threshold <= 100),
                u_threshold REAL NOT NULL CHECK(u_threshold >= 0 AND u_threshold <= 100),
                CHECK(l_threshold < u_threshold)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                latitude REAL NOT NULL CHECK(latitude >= -90 AND latitude <= 90),
                longitude REAL NOT NULL CHECK(longitude >= -180 AND longitude <= 180)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_records_timestamp ON irrigation_records(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_records_location ON irrigation_records(location_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_records_plant ON irrigation_records(plant_name)")

        if cur.execute("SELECT COUNT(*) FROM plants").fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO plants (name, kc, l_threshold, u_threshold) VALUES (?, ?, ?, ?)",
                [(p["name"], p["Kc"], p["L"], p["U"]) for p in DEFAULT_PLANTS],
            )

        existing = {row[0] for row in cur.execute("SELECT key FROM settings")}
        if "pump_flows" not in existing:
            legacy = []
            for index in range(1, 5):
                row = cur.execute("SELECT value FROM settings WHERE key=?", (f"pump_flow_{index}",)).fetchone()
                if row:
                    try:
                        legacy.append(float(json.loads(row[0])))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        legacy = []
                        break
            if len(legacy) == 4:
                cur.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ("pump_flows", json.dumps(legacy)),
                )
                existing.add("pump_flows")
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing:
                cur.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        cur.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def db_health_check():
    try:
        with _connect(readonly=True) as con:
            return con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False


def db_save_setting(key, value):
    key = str(key)
    value = _validated_setting(key, value)
    with _connect() as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
    return True


def db_load_setting(key, default=None):
    try:
        with _connect(readonly=True) as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return _validated_setting(key, json.loads(row[0]))
    except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return default


def db_load_all_settings():
    result = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with _connect(readonly=True) as con:
            rows = con.execute("SELECT key, value FROM settings").fetchall()
    except sqlite3.Error:
        return result
    for key, value in rows:
        try:
            result[key] = _validated_setting(key, json.loads(value))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            print(f"  [DB] Ignoring invalid setting: {key}")
    return result


def db_save_all_settings(settings_dict):
    if not isinstance(settings_dict, dict):
        raise TypeError("settings_dict must be a dictionary")
    values = [
        (str(key), json.dumps(_validated_setting(str(key), value)))
        for key, value in settings_dict.items()
    ]
    with _connect() as con:
        con.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            values,
        )
    return True


def db_get_all_plants():
    with _connect(readonly=True) as con:
        return con.execute(
            "SELECT id, name, kc, l_threshold, u_threshold FROM plants ORDER BY name"
        ).fetchall()


def db_get_plant_by_name(name):
    with _connect(readonly=True) as con:
        return con.execute(
            "SELECT id, name, kc, l_threshold, u_threshold FROM plants WHERE name=?",
            (name,),
        ).fetchone()


def _valid_plant(name, kc, lower, upper):
    name = str(name).strip()
    kc, lower, upper = float(kc), float(lower), float(upper)
    if not name or not all(math.isfinite(value) for value in (kc, lower, upper)):
        raise ValueError("invalid plant parameters")
    if kc <= 0 or not 0 <= lower < upper <= 100:
        raise ValueError("invalid plant parameters")
    return name, kc, lower, upper


def db_add_plant(name, kc, l_thresh, u_thresh):
    values = _valid_plant(name, kc, l_thresh, u_thresh)
    try:
        with _connect() as con:
            con.execute(
                "INSERT INTO plants (name, kc, l_threshold, u_threshold) VALUES (?, ?, ?, ?)",
                values,
            )
        return True
    except sqlite3.IntegrityError:
        return False


def db_update_plant(old_name, name, kc, l_thresh, u_thresh):
    values = _valid_plant(name, kc, l_thresh, u_thresh)
    try:
        with _connect() as con:
            cur = con.execute(
                "UPDATE plants SET name=?, kc=?, l_threshold=?, u_threshold=? WHERE name=?",
                (*values, old_name),
            )
        return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def db_delete_plant(name):
    with _connect() as con:
        cur = con.execute("DELETE FROM plants WHERE name=?", (name,))
    return cur.rowcount > 0


def db_get_all_locations():
    with _connect(readonly=True) as con:
        return con.execute(
            "SELECT id, name, latitude, longitude FROM locations ORDER BY name"
        ).fetchall()


def db_get_location_by_name(name):
    with _connect(readonly=True) as con:
        return con.execute(
            "SELECT id, name, latitude, longitude FROM locations WHERE name=?",
            (name,),
        ).fetchone()


def _valid_location(name, lat, lon):
    name = str(name).strip()
    lat, lon = float(lat), float(lon)
    if not name or not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("invalid location parameters")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("invalid location parameters")
    return name, lat, lon


def db_add_location(name, lat, lon):
    values = _valid_location(name, lat, lon)
    try:
        with _connect() as con:
            con.execute("INSERT INTO locations (name, latitude, longitude) VALUES (?, ?, ?)", values)
        return True
    except sqlite3.IntegrityError:
        return False


def db_update_location(old_name, name, lat, lon):
    values = _valid_location(name, lat, lon)
    try:
        with _connect() as con:
            cur = con.execute(
                "UPDATE locations SET name=?, latitude=?, longitude=? WHERE name=?",
                (*values, old_name),
            )
        return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def db_delete_location(name):
    with _connect() as con:
        cur = con.execute("DELETE FROM locations WHERE name=?", (name,))
    return cur.rowcount > 0


def db_get_history(limit=200):
    with _connect(readonly=True) as con:
        return con.execute(
            f"SELECT {HISTORY_COLUMNS} FROM irrigation_records ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()


def db_get_history_filtered(location=None, date_from=None, date_to=None, limit=200):
    query = f"SELECT {HISTORY_COLUMNS} FROM irrigation_records WHERE 1=1"
    params = []
    if location and location != "All Locations":
        query += " AND location_name=?"
        params.append(location)
    if date_from:
        query += " AND substr(timestamp,1,10)>=?"
        params.append(date_from)
    if date_to:
        query += " AND substr(timestamp,1,10)<=?"
        params.append(date_to)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    with _connect(readonly=True) as con:
        return con.execute(query, params).fetchall()


def db_get_record_by_id(record_id):
    with _connect(readonly=True) as con:
        return con.execute(
            f"SELECT {HISTORY_COLUMNS} FROM irrigation_records WHERE id=?",
            (int(record_id),),
        ).fetchone()


def db_save_record(
    decision,
    soil_data,
    weather,
    source,
    lat,
    lon,
    plant_name="",
    cultivation_mode="Field",
    soil_depth=0.20,
    sample_meta=None,
    pump_states=None,
    pump_times=None,
):
    sample_meta = sample_meta or {}
    pump_states = list(pump_states or [0, 0, 0, 0])
    pump_times = list(pump_times or [0, 0, 0, 0])
    payload = json.dumps(weather, sort_keys=True)
    flows = decision.get("pump_flows", [])
    with _connect() as con:
        cur = con.execute("""
            INSERT INTO irrigation_records (
                timestamp, plant_name, s1, s2, s3, s4, soil_median,
                et0_today, rain_today, rain_next48, temp_min, temp_max,
                kc, area, soil_depth, water_needed_liters, water_final_liters,
                decision_note, weather_source, location_name, latitude, longitude,
                cultivation_mode, water_delivered_estimate_liters,
                irrigation_status, pump_states, pump_times, pump_acknowledged,
                algorithm_version, l_threshold, u_threshold, pump_flows,
                sample_count, sample_started_at, sample_ended_at, weather_payload
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            decision["timestamp"], plant_name,
            soil_data[0], soil_data[1], soil_data[2], soil_data[3], soil_data[4],
            weather["et0"][0], weather["rain"][0], decision["rain_next48"],
            weather["tmin"][0], weather["tmax"][0],
            decision["kc"], decision["area"], soil_depth,
            decision["water_today"], decision["water_final"],
            decision["note"], source, decision["location_name"], lat, lon,
            cultivation_mode, 0.0, "planned",
            json.dumps(pump_states), json.dumps(pump_times), 0,
            decision.get("algorithm_version", "unknown"),
            decision.get("l_threshold"), decision.get("u_threshold"),
            json.dumps(flows), int(sample_meta.get("count", 0)),
            sample_meta.get("started_at"), sample_meta.get("ended_at"), payload,
        ))
        record_id = cur.lastrowid
    _maybe_prune_history()
    return record_id


def db_update_irrigation_result(
    record_id,
    delivered_estimate_liters,
    status,
    pump_states,
    pump_times,
    acknowledged,
):
    with _connect() as con:
        cur = con.execute("""
            UPDATE irrigation_records
            SET water_delivered_estimate_liters=?, irrigation_status=?,
                pump_states=?, pump_times=?, pump_acknowledged=?
            WHERE id=?
        """, (
            max(0.0, float(delivered_estimate_liters)), str(status),
            json.dumps(list(pump_states)), json.dumps(list(pump_times)),
            1 if acknowledged else 0, int(record_id),
        ))
    return cur.rowcount > 0


def db_export_csv(filepath, rows=None):
    export_rows = list(rows) if rows is not None else db_get_history(500)
    header = [column.strip() for column in HISTORY_COLUMNS.split(",")]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(export_rows)
    return len(export_rows)


def db_backup(filepath):
    if os.path.abspath(filepath) == os.path.abspath(DB_FILE):
        raise ValueError("backup destination and source are the same file")
    with _connect(readonly=True) as source, _connect(filepath) as destination:
        source.backup(destination)
    return True


def db_restore(filepath):
    if os.path.abspath(filepath) == os.path.abspath(DB_FILE):
        raise ValueError("restore source and target are the same file")
    with _connect(filepath, readonly=True) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("backup database failed integrity_check")
        required = {"irrigation_records", "plants", "locations", "settings"}
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(tables):
            raise sqlite3.DatabaseError("backup database has an incompatible schema")
        with _connect() as destination:
            source.backup(destination)
    init_database()
    return True


def db_prune_history(keep_days):
    days = max(1, int(keep_days))
    cutoff = time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime(time.time() - days * 86400))
    with _connect() as con:
        cur = con.execute("DELETE FROM irrigation_records WHERE timestamp<?", (cutoff,))
    return cur.rowcount


def _maybe_prune_history():
    global _last_prune_monotonic
    now = time.monotonic()
    if now - _last_prune_monotonic < 86400:
        return
    keep_days = db_load_setting("history_retention_days", 365)
    try:
        days = int(keep_days)
    except (TypeError, ValueError):
        days = int(DEFAULT_SETTINGS["history_retention_days"])
    if days > 0:
        db_prune_history(days)
    _last_prune_monotonic = now
