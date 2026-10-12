// Rainbow showcase; same protocol and wiring as the normal HMI sketch.
#define GERM_DEFAULT_RAINBOW 1
// GERM Uno: existing HMI command names, actual wiring, and output feedback.
#include <stdlib.h>
#include <string.h>
#ifndef GERM_DEFAULT_RAINBOW
#define GERM_DEFAULT_RAINBOW 0
#endif
const byte FAN_PIN = 2, PUMP_PIN = 8;
const byte LED_R = 5, LED_G = 6, LED_B = 9;
// Existing showcase wiring uses inverted RGB PWM. Pump is direct N-channel gate.
bool fanOn = false, pumpOn = false;
byte r = 0, g = 0, b = 0;
unsigned long lastContact = 0, pumpStarted = 0, pumpDuration = 30000;
char buffer[80];
byte used = 0;
bool overflow = false;
bool rainbow = false;
unsigned long rainbowPrevious = 0;
unsigned int hue = 0;

// One hue degree every 20 ms; never block serial, fan, or pump handling.
void updateRainbow(unsigned long now) {
  if (!rainbow || now - rainbowPrevious < 20UL) return;
  rainbowPrevious = now;
  byte rising = (hue % 60) * 255UL / 60;
  byte falling = 255 - rising;
  switch (hue / 60) {
    case 0: r = 255; g = rising; b = 0; break;
    case 1: r = falling; g = 255; b = 0; break;
    case 2: r = 0; g = 255; b = rising; break;
    case 3: r = 0; g = falling; b = 255; break;
    case 4: r = rising; g = 0; b = 255; break;
    case 5: r = 255; g = 0; b = falling; break;
  }
  hue = (hue + 1) % 360;
  outputs();
}

void outputs() {
  digitalWrite(FAN_PIN, fanOn ? HIGH : LOW);
  digitalWrite(PUMP_PIN, pumpOn ? HIGH : LOW);
  analogWrite(LED_R, 255 - r);
  analogWrite(LED_G, 255 - g);
  analogWrite(LED_B, 255 - b);
}
void stopAll() { rainbow = false; fanOn = pumpOn = false; r = g = b = 0; outputs(); }
void reply(unsigned int id, const char *error) {
  Serial.print(F("{\"protocol\":2,\"id\":")); Serial.print(id);
  Serial.print(F(",\"fan\":")); Serial.print(fanOn ? F("true") : F("false"));
  Serial.print(F(",\"pump\":")); Serial.print(pumpOn ? F("true") : F("false"));
  Serial.print(F(",\"rgb\":[")); Serial.print(r); Serial.print(','); Serial.print(g); Serial.print(','); Serial.print(b);
  Serial.print(F("],\"a0\":null,\"fan_pwm\":false,\"white_channel\":false"));
  Serial.print(F(",\"lighting_mode\":\"")); Serial.print(rainbow ? F("rainbow") : F("normal")); Serial.print('"');
  if (error) { Serial.print(F(",\"error\":\"")); Serial.print(error); Serial.print('"'); }
  Serial.println('}');
}
bool parseNumber(const char *s, unsigned int maxValue, unsigned int &n) {
  if (!s || !*s || strlen(s) > 5) return false;
  for (const char *p = s; *p; ++p) if (*p < '0' || *p > '9') return false;
  unsigned long v = strtoul(s, NULL, 10);
  if (v > maxValue) return false;
  n = (unsigned int)v; return true;
}
void handleCommand(char *cmd) {
  unsigned int id = 0;
  if (!strncmp(cmd, "CMD:", 4)) {
    char *separator = strchr(cmd + 4, ':');
    if (!separator) { reply(0, "Invalid command ID"); return; }
    *separator = '\0';
    if (!parseNumber(cmd + 4, 60000, id) || !id) { reply(0, "Invalid command ID"); return; }
    cmd = separator + 1;
  }
  const char *error = NULL;
  if (!strcmp(cmd, "STATUS")) {}
  else if (!strcmp(cmd, "STOP")) stopAll();
  else if (!strcmp(cmd, "FAN_ON")) fanOn = true;
  else if (!strcmp(cmd, "FAN_OFF")) fanOn = false;
  else if (!strncmp(cmd, "FAN_SPEED:", 10)) {
    unsigned int speed;
    if (!parseNumber(cmd + 10, 255, speed) || (speed != 0 && speed != 255)) error = "D2 supports fan on/off only";
    else fanOn = speed == 255;
  }
  else if (!strcmp(cmd, "PUMP_OFF")) pumpOn = false;
  else if (!strcmp(cmd, "PUMP_ON") || !strcmp(cmd, "PUMP_5S")) {
    unsigned long duration = !strcmp(cmd, "PUMP_5S") ? 5000UL : 30000UL;
    if (!pumpOn) { pumpStarted = millis(); pumpDuration = duration; }
    else if (duration < pumpDuration) pumpDuration = duration;
    pumpOn = true;
  }
  else if (!strcmp(cmd, "MODE:rainbow")) { rainbow = true; hue = 0; rainbowPrevious = millis() - 20UL; updateRainbow(millis()); }
  else if (!strcmp(cmd, "MODE:normal")) { rainbow = false; r = g = b = 0; }
  else if (!strcmp(cmd, "LED_OFF")) { rainbow = false; r = g = b = 0; }
  else if (!strcmp(cmd, "LED_ON")) { rainbow = false; r = g = b = 255; }
  else if (!strncmp(cmd, "LED:", 4)) {
    unsigned int channels[4];
    char *cursor = cmd + 4;
    bool valid = true;
    for (byte i = 0; i < 4; ++i) {
      char *comma = strchr(cursor, ',');
      if ((i < 3 && !comma) || (i == 3 && comma)) { valid = false; break; }
      if (comma) *comma = '\0';
      if (!parseNumber(cursor, 255, channels[i])) { valid = false; break; }
      if (comma) cursor = comma + 1;
    }
    if (!valid) error = "Invalid RGB values";
    else if (channels[3] != 0) error = "No separate white channel; use RGB";
    else { rainbow = false; r = channels[0]; g = channels[1]; b = channels[2]; }
  }
  else error = "Unknown command";
  if (!error) { lastContact = millis(); outputs(); }
  reply(id, error);
}
void setup() {
  digitalWrite(FAN_PIN, LOW); digitalWrite(PUMP_PIN, LOW);
  pinMode(FAN_PIN, OUTPUT); pinMode(PUMP_PIN, OUTPUT);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  stopAll(); Serial.begin(9600); lastContact = millis();
  rainbow = GERM_DEFAULT_RAINBOW;
}
void loop() {
  unsigned long now = millis();
  if (now - lastContact >= 10000UL) stopAll();
  if (pumpOn && now - pumpStarted >= pumpDuration) { pumpOn = false; outputs(); }
  updateRainbow(now);
  for (byte count = 0; count < 64 && Serial.available(); ++count) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow) reply(0, "Command too long");
      else { buffer[used] = '\0'; handleCommand(buffer); }
      used = 0; overflow = false;
    } else if (!overflow && used < sizeof(buffer) - 1) buffer[used++] = c;
    else overflow = true;
  }
}
