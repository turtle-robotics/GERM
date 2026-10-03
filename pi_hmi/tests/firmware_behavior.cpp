// Host-side behavior checks: g++ -std=c++11 tests/firmware_behavior.cpp -o /tmp/germ-firmware-test
#include <cassert>
#include <sstream>
#include <cstring>
using byte = unsigned char;
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define F(value) value
unsigned long clockMs = 0;
int pins[20] = {};
unsigned long millis() { return clockMs; }
void digitalWrite(int pin, int value) { pins[pin] = value; }
void analogWrite(int pin, int value) { pins[pin] = value; }
void pinMode(int, int) {}
struct SerialStub {
  std::ostringstream output;
  void begin(int) {}
  int available() { return 0; }
  char read() { return 0; }
  void print(byte value) { output << int(value); }
  template<typename T> void print(T value) { output << value; }
  template<typename T> void println(T value) { output << value << '\n'; }
} Serial;
void outputs();
#include "../arduino_program/arduino_program.ino"
void command(const char *value) {
  char input[80]; strcpy(input, value); handleCommand(input);
}
int main() {
  setup();
  assert(FAN_PIN == 2 && PUMP_PIN == 8 && LED_R == 3 && LED_G == 6 && LED_B == 9);
  assert(!fanOn && !pumpOn && pins[3] == 255);
  command("CMD:1:MODE:rainbow");
  assert(rainbow && r == 255 && g == 0 && b == 0 && pins[3] == 0);
  clockMs = 20; loop(); assert(g > 0 && rainbow);
  command("CMD:2:FAN_ON"); assert(fanOn && rainbow && pins[2] == HIGH);
  command("CMD:3:PUMP_5S"); assert(pumpOn && rainbow && pins[8] == HIGH);
  clockMs = 4000; command("CMD:4:STATUS");
  clockMs = 5020; loop(); assert(!pumpOn && rainbow && fanOn);
  command("CMD:5:LED:0,0,0,0"); assert(!rainbow && pins[3] == 255);
  command("CMD:6:MODE:rainbow");
  command("CMD:7:LED:1,2,3,0"); assert(!rainbow && r == 1 && g == 2 && b == 3);
  command("CMD:8:MODE:rainbow"); command("CMD:9:MODE:invalid"); assert(rainbow);
  command("CMD:10:MODE:normal"); assert(!rainbow && r == 0);
  command("CMD:11:MODE:rainbow"); command("CMD:12:PUMP_ON");
  for (int i = 0; i < 6; ++i) { clockMs += 5000; command("CMD:13:STATUS"); loop(); }
  assert(!pumpOn && rainbow);
  clockMs += 10000; loop(); assert(!rainbow && !fanOn && !pumpOn && r == 0);
  command("CMD:14:MODE:rainbow"); command("CMD:15:STOP"); assert(!rainbow && r == 0);
}
