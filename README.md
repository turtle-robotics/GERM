# GERM

Automated plant growing box with an Arduino Uno and a Raspberry Pi touchscreen HMI.

The complete source exported from the working Pi HMI is in [`pi_hmi/`](pi_hmi/README.md).
It includes Flask routes, the seven-screen interface, camera and sensor readers,
serial control with firmware acknowledgements, Arduino firmware uploads, the
Uno sketch, systemd boot configuration, and the Chromium kiosk launcher.

Start with the [Pi reproduction guide](pi_hmi/README.md). See the
[publication security review](pi_hmi/SECURITY.md) for what was checked and excluded.

Select **Normal HMI control** or **Rainbow** in **Controls → Lighting**, then
press **Upload selected mode**. Both use fan D2, pump D8, and RGB D5/D6/D9.
The root `Showcase LED Display.ino` is the protocol-2 rainbow variant;
`pi_hmi/arduino_program/arduino_program.ino` defaults to normal HMI control.
Both retain fan/pump controls, LED Off, and the same timeouts.
