import math
import os
import select
import subprocess
import threading
import time


STATE_COLLECT = "COLLECT"
STATE_DECIDE = "DECIDE"
STATE_IRRIGATE = "IRRIGATE"
STATE_STOPPED = "STOPPED"
STATE_ERROR = "ERROR"

BAUD = 115200
CONFIGURED_PORT = "auto"
COLLECT_DURATION = 60
SENSOR_TIMEOUT_SECONDS = 15.0
SENSOR_SAMPLE_INTERVAL_SECONDS = 2.0
HANDSHAKE_TIMEOUT_SECONDS = 5.0

soil_samples = []
soil_samples_lock = threading.Lock()
serial_lock = threading.Lock()
state_lock = threading.Lock()
latest_data_lock = threading.Lock()
reader_start_lock = threading.Lock()

serial_port = None
current_port_name = None
latest_soil_data = None
latest_soil_monotonic = None
system_state = STATE_STOPPED
sensor_reader_started = False
sensor_stream_expected = False
device_verified = False
_sensor_stream_started_monotonic = None

_connection_callbacks = []
_receive_buffer = bytearray()
_command_sequence = 0
_pending_pump_acks = {}
_pending_ack_lock = threading.Lock()
_pump_command_gate_lock = threading.Lock()
_pump_commands_enabled = False
_heartbeat_ack_event = threading.Event()
safety_stop_event = threading.Event()
last_safety_stop_reason = None


class SerialProtocolError(ValueError):
    pass


def on_connection_change(callback):
    if callback not in _connection_callbacks:
        _connection_callbacks.append(callback)


def _notify_connection(connected, port_name=""):
    for callback in tuple(_connection_callbacks):
        try:
            callback(bool(connected), port_name or "")
        except Exception as exc:
            print(f"  [SERIAL] Connection callback failed: {exc}")


def set_system_state(state):
    global system_state
    if state not in {STATE_COLLECT, STATE_DECIDE, STATE_IRRIGATE, STATE_STOPPED, STATE_ERROR}:
        raise ValueError(f"Unknown sensor state: {state}")
    with state_lock:
        system_state = state


def get_system_state():
    with state_lock:
        return system_state


def get_latest_soil_data():
    with latest_data_lock:
        return latest_soil_data


def get_latest_soil_age():
    with latest_data_lock:
        if latest_soil_monotonic is None:
            return None
        return max(0.0, time.monotonic() - latest_soil_monotonic)


def clear_latest_soil_data():
    global latest_soil_data, latest_soil_monotonic
    with latest_data_lock:
        latest_soil_data = None
        latest_soil_monotonic = None


def configure_serial(port=None, baud=None, reconnect=True):
    global CONFIGURED_PORT, BAUD
    changed = False
    if port is not None:
        value = str(port).strip() or "auto"
        changed = changed or value != CONFIGURED_PORT
        CONFIGURED_PORT = value
    if baud is not None:
        value = int(baud)
        if value <= 0:
            raise ValueError("baud must be positive")
        changed = changed or value != BAUD
        BAUD = value
    if changed and reconnect and serial_port is not None:
        disconnect_serial(send_stop=True)


def find_serial_port():
    if CONFIGURED_PORT.lower() != "auto":
        return CONFIGURED_PORT if os.path.exists(CONFIGURED_PORT) else None
    try:
        devices = sorted(os.listdir("/dev"))
    except OSError:
        return None
    candidates = [
        f"/dev/{name}"
        for name in devices
        if name.startswith("ttyUSB") or name.startswith("ttyACM")
    ]
    return candidates[0] if candidates else None


def _configure_terminal(port):
    result = subprocess.run(
        ["stty", "-F", port, str(BAUD), "raw", "-echo"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "stty failed"
        raise OSError(message)


def _write_locked(payload):
    if serial_port is None:
        return False
    serial_port.write(payload)
    if hasattr(serial_port, "flush"):
        serial_port.flush()
    return True


def connect_serial():
    global serial_port, current_port_name, device_verified, _receive_buffer
    port = find_serial_port()
    if not port:
        return None
    try:
        _configure_terminal(port)
        opened = open(port, "r+b", buffering=0)
        os.set_blocking(opened.fileno(), False)
        with serial_lock:
            if serial_port is not None:
                try:
                    serial_port.close()
                except OSError:
                    pass
            serial_port = opened
            current_port_name = port
            device_verified = False
            _receive_buffer = bytearray()
            _write_locked(b"PING\n")
        return port
    except Exception as exc:
        print(f"  [SERIAL] Connection failed: {exc}")
        _notify_connection(False, port)
        return None


def _close_serial(notify=True):
    global serial_port, current_port_name, device_verified
    with serial_lock:
        port_name = current_port_name
        if serial_port is not None:
            try:
                serial_port.close()
            except OSError:
                pass
        serial_port = None
        current_port_name = None
        device_verified = False
    if notify:
        _notify_connection(False, port_name or "")


def disconnect_serial(send_stop=True):
    if send_stop:
        safe_stop_pumps(retries=2, wait_ack=False)
    _close_serial(notify=True)


def send_serial_command(command):
    global sensor_stream_expected, _sensor_stream_started_monotonic
    text = str(command).strip()
    if not text or "\n" in text or "\r" in text:
        raise SerialProtocolError("serial command must contain one line")
    try:
        with serial_lock:
            sent = _write_locked((text + "\n").encode("ascii"))
        if sent and text == "SENSOR:START":
            sensor_stream_expected = True
            _sensor_stream_started_monotonic = time.monotonic()
        elif sent and text == "SENSOR:STOP":
            sensor_stream_expected = False
            _sensor_stream_started_monotonic = None
        return sent
    except Exception as exc:
        print(f"  [SERIAL] Send failed: {exc}")
        _close_serial(notify=True)
        return False


def send_heartbeat(wait_ack=True, timeout=2.0):
    _heartbeat_ack_event.clear()
    if not send_serial_command("HEARTBEAT"):
        return False
    if not wait_ack:
        return True
    return _heartbeat_ack_event.wait(max(0.05, float(timeout)))


def enable_pump_commands():
    global _pump_commands_enabled
    with _pump_command_gate_lock:
        _pump_commands_enabled = True


def disable_pump_commands():
    global _pump_commands_enabled
    with _pump_command_gate_lock:
        _pump_commands_enabled = False


def _next_sequence():
    global _command_sequence
    with _pending_ack_lock:
        _command_sequence = (_command_sequence + 1) % 1_000_000
        return _command_sequence


def send_pump_command(p1, p2, p3, p4, wait_ack=True, timeout=2.0):
    global last_safety_stop_reason
    states = tuple(1 if bool(value) else 0 for value in (p1, p2, p3, p4))
    with _pump_command_gate_lock:
        if any(states) and (not _pump_commands_enabled or not device_verified):
            return False
        if any(states):
            safety_stop_event.clear()
            last_safety_stop_reason = None
        sequence = _next_sequence()
        event = threading.Event()
        with _pending_ack_lock:
            _pending_pump_acks[sequence] = {"event": event, "states": None}
        command = f"PUMP:{sequence}:{','.join(str(value) for value in states)}"
        if not send_serial_command(command):
            with _pending_ack_lock:
                _pending_pump_acks.pop(sequence, None)
            return False
    if not wait_ack:
        with _pending_ack_lock:
            _pending_pump_acks.pop(sequence, None)
        return True
    acknowledged = event.wait(max(0.05, float(timeout)))
    with _pending_ack_lock:
        result = _pending_pump_acks.pop(sequence, None)
    return bool(acknowledged and result and result.get("states") == states)


def safe_stop_pumps(retries=3, wait_ack=True):
    success = False
    for _ in range(max(1, int(retries))):
        success = send_pump_command(0, 0, 0, 0, wait_ack=wait_ack, timeout=1.0)
        if success:
            return True
        time.sleep(0.05)
    return success


def parse_sensor_line(line):
    parts = str(line).strip().split(",")
    if len(parts) != 4:
        raise SerialProtocolError("sensor line must contain four values")
    values = []
    for index, part in enumerate(parts):
        try:
            value = float(part)
        except ValueError as exc:
            raise SerialProtocolError(f"sensor {index + 1} is not numeric") from exc
        if not math.isfinite(value) or not 0.0 <= value <= 100.0:
            raise SerialProtocolError(f"sensor {index + 1} is outside 0..100")
        values.append(value)
    ordered = sorted(values)
    median = (ordered[1] + ordered[2]) / 2.0
    return (*values, median)


def aggregate_soil_samples(samples, minimum_samples=3):
    minimum = max(1, int(minimum_samples))
    rows = list(samples)
    if len(rows) < minimum:
        raise SerialProtocolError(
            f"insufficient sensor data: {len(rows)} of {minimum} samples"
        )
    validated = []
    for row_index, row in enumerate(rows):
        if len(row) < 4:
            raise SerialProtocolError(f"sample {row_index + 1} has fewer than four values")
        values = []
        for index in range(4):
            value = float(row[index])
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise SerialProtocolError(f"sample {row_index + 1}, sensor {index + 1} is invalid")
            values.append(value)
        validated.append(values)
    averages = [
        sum(row[index] for row in validated) / len(validated)
        for index in range(4)
    ]
    ordered = sorted(averages)
    return (*averages, (ordered[1] + ordered[2]) / 2.0)


def _resolve_pump_ack(line):
    # PUMP OK:<sequence>:s1,s2,s3,s4
    fields = line.split(":", 2)
    if len(fields) != 3 or fields[0] != "PUMP OK":
        return False
    try:
        sequence = int(fields[1])
        states = tuple(int(value) for value in fields[2].split(","))
    except ValueError:
        return False
    if len(states) != 4 or any(value not in (0, 1) for value in states):
        return False
    with _pending_ack_lock:
        pending = _pending_pump_acks.get(sequence)
        if pending:
            pending["states"] = states
            pending["event"].set()
    return True


def process_serial_line(line):
    global latest_soil_data, latest_soil_monotonic, device_verified, last_safety_stop_reason
    text = line.strip()
    if not text:
        return None
    if text == "PONG:STM32_IRRIGATION_V1":
        device_verified = True
        _notify_connection(True, current_port_name or "")
        return "handshake"
    if _resolve_pump_ack(text):
        return "pump_ack"
    if text.startswith("SAFETY STOP:"):
        last_safety_stop_reason = text.partition(":")[2] or "UNKNOWN"
        safety_stop_event.set()
        return "safety_stop"
    if text == "HEARTBEAT OK":
        _heartbeat_ack_event.set()
        return "heartbeat_ack"
    if text in ("SENSOR ON", "SENSOR OFF"):
        return "status"
    data = parse_sensor_line(text)
    with latest_data_lock:
        latest_soil_data = data
        latest_soil_monotonic = time.monotonic()
    if get_system_state() == STATE_COLLECT:
        with soil_samples_lock:
            soil_samples.append(data[:4])
    return data


def _read_available(port_ref):
    try:
        return os.read(port_ref.fileno(), 512)
    except BlockingIOError:
        return b""


def sensor_reader():
    global _receive_buffer
    last_data_time = time.monotonic()
    handshake_started = None
    while True:
        try:
            if serial_port is None:
                port = connect_serial()
                if not port:
                    time.sleep(2)
                    continue
                handshake_started = time.monotonic()
                last_data_time = time.monotonic()

            with serial_lock:
                port_ref = serial_port
            if port_ref is None:
                continue

            readable, _, _ = select.select([port_ref], [], [], 1.0)
            if readable:
                chunk = _read_available(port_ref)
                if not chunk:
                    raise OSError("serial device closed")
                _receive_buffer.extend(chunk)
                while b"\n" in _receive_buffer:
                    raw_line, _, remainder = _receive_buffer.partition(b"\n")
                    _receive_buffer = bytearray(remainder)
                    line = raw_line.decode("ascii", errors="replace").strip("\r")
                    try:
                        result = process_serial_line(line)
                        if isinstance(result, tuple):
                            last_data_time = time.monotonic()
                    except SerialProtocolError as exc:
                        print(f"  [SENSOR] Invalid line: {exc}")

            now = time.monotonic()
            if not device_verified and handshake_started is not None and now - handshake_started > HANDSHAKE_TIMEOUT_SECONDS:
                raise SerialProtocolError("device handshake timeout")
            if sensor_stream_expected and get_system_state() == STATE_COLLECT:
                with latest_data_lock:
                    stream_reference = latest_soil_monotonic
                if stream_reference is None:
                    stream_reference = _sensor_stream_started_monotonic
                if stream_reference is not None and now - stream_reference > SENSOR_TIMEOUT_SECONDS:
                    raise SerialProtocolError("sensor data timeout")
        except Exception as exc:
            print(f"  [SERIAL] Reader error: {exc}")
            _close_serial(notify=True)
            time.sleep(1)


def start_sensor_reader():
    global sensor_reader_started
    with reader_start_lock:
        if sensor_reader_started:
            return False
        threading.Thread(target=sensor_reader, daemon=True, name="sensor-reader").start()
        sensor_reader_started = True
        return True


def format_minutes_to_mmss(minutes):
    value = max(0.0, float(minutes))
    total_seconds = int(round(value * 60.0))
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"
