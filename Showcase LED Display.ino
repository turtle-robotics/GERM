#include <DHT.h>

/*
  Non-blocking RGB LED + Fan Demo
  Inverted PWM: 0 = full brightness, 255 = off
*/

// --------------------
// PIN DEFINITIONS
// --------------------
const int FAN_PIN     = 2;
const int LED_R_PIN   = 5;
const int LED_G_PIN   = 6;
const int LED_B_PIN   = 9;

const int DHT_PIN     = 12;
const int DHT_TYPE    = DHT11;

// --------------------
// DIMMING
// --------------------
const int DIM_MAX = 200;

// --------------------
// GLOBAL STATE
// --------------------
unsigned long currentMillis;

// Rainbow animation
unsigned long rainbowPrevMillis = 0;
const int rainbowSpeed = 20;
int hue = 0;

// Fan cycle
unsigned long fanPrevMillis = 0;
bool fanState = false;
const unsigned long fanOnTime  = 10000;
const unsigned long fanOffTime = 5000;

// DHT timing
unsigned long dhtPrevMillis = 0;
const unsigned long dhtInterval = 2000; // 2 seconds

DHT dht(DHT_PIN, DHT_TYPE);

// --------------------
// HSV → RGB
// --------------------
void hsvToRgb(int H, float& r, float& g, float& b) {
  float h = H / 60.0;
  int i = (int)h;
  float f = h - i;
  float q = 1 - f;

  switch (i % 6) {
    case 0: r = 1; g = f; b = 0; break;
    case 1: r = q; g = 1; b = 0; break;
    case 2: r = 0; g = 1; b = f; break;
    case 3: r = 0; g = q; b = 1; break;
    case 4: r = f; g = 0; b = 1; break;
    case 5: r = 1; g = 0; b = q; break;
  }
}

// --------------------
// RAINBOW UPDATE
// --------------------
void updateRainbow() {
  if (currentMillis - rainbowPrevMillis >= rainbowSpeed) {
    rainbowPrevMillis = currentMillis;

    float r, g, b;
    hsvToRgb(hue, r, g, b);

    int R = DIM_MAX - int(r * (DIM_MAX - 255));
    int G = DIM_MAX - int(g * (DIM_MAX - 255));
    int B = DIM_MAX - int(b * (DIM_MAX - 255));

    analogWrite(LED_R_PIN, R);
    analogWrite(LED_G_PIN, G);
    analogWrite(LED_B_PIN, B);

    hue = (hue + 1) % 360;
  }
}

// --------------------
// FAN UPDATE
// --------------------
void updateFan() {
  unsigned long interval = fanState ? fanOnTime : fanOffTime;

  if (currentMillis - fanPrevMillis >= interval) {
    fanPrevMillis = currentMillis;
    fanState = !fanState;
    digitalWrite(FAN_PIN, fanState ? HIGH : LOW);
  }
}

// --------------------
// DHT READ + SERIAL OUTPUT
// --------------------
void updateDHT() {
  if (currentMillis - dhtPrevMillis >= dhtInterval) {
    dhtPrevMillis = currentMillis;

    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature(); // Celsius

    if (isnan(humidity) || isnan(temperature)) {
      Serial.println("DHT11 read failed");
      return;
    }

    Serial.print("Humidity: ");
    Serial.print(humidity);
    Serial.print(" % | Temperature: ");
    Serial.print(temperature);
    Serial.println(" °C");
  }
}

// --------------------
// SETUP
// --------------------
void setup() {
  pinMode(FAN_PIN, OUTPUT);
  pinMode(LED_R_PIN, OUTPUT);
  pinMode(LED_G_PIN, OUTPUT);
  pinMode(LED_B_PIN, OUTPUT);

  digitalWrite(FAN_PIN, LOW);

  Serial.begin(9600);
  dht.begin();

  Serial.println("Starting ultra-dim rainbow LED + Fan + DHT11 Demo");
}

// --------------------
// MAIN LOOP
// --------------------
void loop() {
  currentMillis = millis();

  updateRainbow();
  updateFan();
  updateDHT();
}
