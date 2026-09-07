#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
bool displayReady = false;

const int relayPins[4] = { PB0, PB1, PB10, PB11 };

const bool RELAY_ACTIVE_LEVEL = LOW;
const bool RELAY_INACTIVE_LEVEL = HIGH;

const int sensorPins[4] = { PA0, PA1, PA2, PA3 };

int dry_thresholds[4] = { 3000, 3000, 3000, 3000 };
int wet_thresholds[4] = { 1200, 1200, 1200, 1200 };

String serialBuffer = "";

bool sensorEnabled = true;

unsigned long lastSend = 0;
const unsigned long SEND_INTERVAL = 2000;

// ---------------- Pump status ----------------
bool pumpStates[4] = { false, false, false, false };
bool pumpCommandReceived = false;
unsigned long lastControlHeartbeat = 0;
unsigned long pumpStartedAt[4] = { 0, 0, 0, 0 };
const unsigned long COMMAND_WATCHDOG_MS = 15000;
const unsigned long MAX_CONTINUOUS_PUMP_MS = 30UL * 60UL * 1000UL;

// =====================================================

void setPumps(bool p1, bool p2, bool p3, bool p4) {

  bool states[4] = { p1, p2, p3, p4 };

  for (int i = 0; i < 4; i++) {

    if (states[i] && !pumpStates[i]) {
      pumpStartedAt[i] = millis();
    }
    if (!states[i]) {
      pumpStartedAt[i] = 0;
    }

    digitalWrite(
      relayPins[i],
      states[i] ? RELAY_ACTIVE_LEVEL : RELAY_INACTIVE_LEVEL);

    pumpStates[i] = states[i];
  }

  pumpCommandReceived = true;
  lastControlHeartbeat = millis();
}

void stopAllPumps() {
  setPumps(false, false, false, false);
}

bool anyPumpRunning() {
  for (int i = 0; i < 4; i++) {
    if (pumpStates[i]) return true;
  }
  return false;
}

void enforcePumpSafety() {
  if (!anyPumpRunning()) return;

  if (millis() - lastControlHeartbeat > COMMAND_WATCHDOG_MS) {
    stopAllPumps();
    Serial.println("SAFETY STOP:WATCHDOG");
    return;
  }

  for (int i = 0; i < 4; i++) {
    if (pumpStates[i] && millis() - pumpStartedAt[i] > MAX_CONTINUOUS_PUMP_MS) {
      stopAllPumps();
      Serial.println("SAFETY STOP:MAX_RUNTIME");
      return;
    }
  }
}

// =====================================================

int getMoisturePercent(int raw, int dry, int wet) {

  int val = map(raw, dry, wet, 0, 100);

  return constrain(val, 0, 100);
}

// =====================================================

String getMoistureStatus(int percent) {

  if (percent < 25) return "DRY";
  if (percent > 75) return "WET";

  return "MID";
}

// =====================================================

void handleSerialCommand(String cmd) {

  cmd.trim();

  if (cmd == "PING") {
    Serial.println("PONG:STM32_IRRIGATION_V1");
    return;
  }

  if (cmd == "HEARTBEAT") {
    lastControlHeartbeat = millis();
    Serial.println("HEARTBEAT OK");
    return;
  }

  // ---------- SENSOR START ----------
  if (cmd == "SENSOR:START") {

    sensorEnabled = true;

    Serial.println("SENSOR ON");

    return;
  }

  // ---------- SENSOR STOP ----------
  if (cmd == "SENSOR:STOP") {

    sensorEnabled = false;

    Serial.println("SENSOR OFF");

    return;
  }

  // ---------- PUMP COMMAND ----------
  if (!cmd.startsWith("PUMP:")) return;

  cmd.remove(0, 5);

  int sequenceSeparator = cmd.indexOf(':');
  if (sequenceSeparator <= 0) return;
  String sequence = cmd.substring(0, sequenceSeparator);
  for (unsigned int i = 0; i < sequence.length(); i++) {
    if (!isDigit(sequence.charAt(i))) return;
  }
  cmd = cmd.substring(sequenceSeparator + 1);
  if (cmd.length() == 0 || cmd.endsWith(",")) return;

  int vals[4] = { 0, 0, 0, 0 };

  int idx = 0;

  while (cmd.length() > 0 && idx < 4) {

    int commaIndex = cmd.indexOf(',');

    String part;

    if (commaIndex == -1) {

      part = cmd;
      cmd = "";

    } else {

      part = cmd.substring(0, commaIndex);
      cmd = cmd.substring(commaIndex + 1);
    }

    part.trim();
    if (part != "0" && part != "1") return;
    vals[idx] = part.toInt();

    idx++;
  }

  if (idx == 4 && cmd.length() == 0) {

    for (int i = 0; i < 4; i++) {
      if (vals[i] != 0 && vals[i] != 1) return;
    }

    setPumps(
      vals[0],
      vals[1],
      vals[2],
      vals[3]);

    Serial.print("PUMP OK:");
    Serial.print(sequence);
    Serial.print(":");
    Serial.print(vals[0]);
    Serial.print(",");
    Serial.print(vals[1]);
    Serial.print(",");
    Serial.print(vals[2]);
    Serial.print(",");
    Serial.println(vals[3]);
  }
}

// =====================================================

void readSerialNonBlocking() {

  while (Serial.available() > 0) {

    char c = Serial.read();

    if (c == '\n') {

      handleSerialCommand(serialBuffer);

      serialBuffer = "";
    }

    else if (c != '\r') {

      serialBuffer += c;

      if (serialBuffer.length() > 64) {

        serialBuffer = "";
      }
    }
  }
}

// =====================================================

void drawHeader() {

  display.setTextSize(1);

  display.setCursor(0, 0);

  display.print("SYS:");

  if (sensorEnabled) {

    display.print("ONLINE");

  } else {

    display.print("PAUSED");
  }

  display.setCursor(78, 0);

  display.print("P:");

  if (!pumpCommandReceived) {

    display.print("-- -- -- --");

  } else {

    for (int i = 0; i < 4; i++) {

      display.print(pumpStates[i] ? "1 " : "0 ");
    }
  }

  display.drawLine(0, 10, 127, 10, WHITE);
}

// =====================================================

void drawSoilData(int percentages[4]) {

  for (int i = 0; i < 4; i++) {

    int y = 14 + (i * 12);

    String status = getMoistureStatus(percentages[i]);

    display.setCursor(0, y);

    display.print("S");
    display.print(i + 1);

    display.print(":");

    if (percentages[i] < 10)
      display.print(" ");

    display.print(percentages[i]);

    display.print("%");

    display.setCursor(60, y);

    display.print(status);

    // -------- mini moisture bar --------
    int barWidth = map(percentages[i], 0, 100, 0, 40);

    display.drawRect(84, y, 40, 8, WHITE);

    display.fillRect(84, y, barWidth, 8, WHITE);
  }
}

// =====================================================

void setup() {

  Serial.begin(115200);

  Serial.setTimeout(50);
  serialBuffer.reserve(96);

  analogReadResolution(12);

  displayReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  if (displayReady) display.clearDisplay();

  if (displayReady) display.setTextColor(WHITE);

  if (displayReady) display.setTextSize(1);

  for (int i = 0; i < 4; i++) {

    pinMode(relayPins[i], OUTPUT);

    digitalWrite(
      relayPins[i],
      RELAY_INACTIVE_LEVEL);
  }

  // ---------- Boot Screen ----------
  if (displayReady) display.clearDisplay();

  if (displayReady) {
    display.setCursor(20, 20);
    display.setTextSize(2);
    display.println("SMART");

    display.setCursor(10, 42);
    display.setTextSize(1);
    display.println("Irrigation System");

    display.display();
  }

  delay(2000);
}

// =====================================================

void loop() {

  readSerialNonBlocking();
  enforcePumpSafety();

  if (millis() - lastSend >= SEND_INTERVAL) {

    lastSend = millis();

    if (displayReady) {
      display.clearDisplay();
      drawHeader();
    }

    // ======================================
    // SENSOR ACTIVE
    // ======================================

    if (sensorEnabled) {

      int percentages[4];

      for (int i = 0; i < 4; i++) {

        int rawValue = analogRead(sensorPins[i]);

        percentages[i] = getMoisturePercent(
          rawValue,
          dry_thresholds[i],
          wet_thresholds[i]);
      }

      if (displayReady) drawSoilData(percentages);

      // -------- Send data to BTT --------

      Serial.print(percentages[0]);
      Serial.print(",");

      Serial.print(percentages[1]);
      Serial.print(",");

      Serial.print(percentages[2]);
      Serial.print(",");

      Serial.println(percentages[3]);
    }

    // ======================================
    // SENSOR PAUSED
    // ======================================

    else {

      if (displayReady) {
        display.setTextSize(2);
        display.setCursor(10, 28);
        display.println("PAUSED");
      }
    }

    if (displayReady) display.display();
  }
}
