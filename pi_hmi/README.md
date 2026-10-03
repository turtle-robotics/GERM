# GERM Raspberry Pi HMI

This is a complete export of the application running in `/home/germ/hmi_flask`
on the GERM Raspberry Pi. The application code and assets include the lighting-mode update deployed on
October 3, 2026. `environment/source-sha256.json` records the current application
hashes; the package inventories still describe the original export. Boot and
kiosk files were exported separately. Setup instructions and verification tools
are included alongside that source.

## Included functionality

- Seven local screens: Home, Plant + Camera, Trends, Controls, Alerts,
  Maintenance, and Settings.
- Picamera2/OpenCV camera snapshots and manual JPEG capture.
- Pi DHT11 readings with explicit missing/stale/fresh states.
- Arduino fan, RGB, and pump commands with matched firmware acknowledgements.
- Settings → Arduino firmware upload, supporting built-in or single-file `.ino`
  sketches through Arduino CLI.
- Existing systemd autostart and labwc/Chromium touchscreen kiosk setup.

Database and ML adapters are intentionally placeholders, exactly as on the Pi.
Camera and environmental sensor readings were unavailable when this export was
verified; the code supports those devices when correctly connected. There is no
water-temperature sensor, motion feedback, separate white LED channel, or
connected E-STOP status signal. The HMI reports these limits rather than
inventing readings. A software output setting does not prove physical operation.

## Hardware and wiring

The exported environment uses Raspberry Pi OS based on Debian 13 (trixie),
Python 3.13.5, an IMX500 AI Camera, and an Arduino Uno over USB. Recorded package
versions are in `environment/pi-system-packages.txt` and
`environment/pi-packages.freeze.txt`. The latter includes system Python packages
visible to the virtual environment; it is an inventory, **not** a pip install
requirements file.

| Device | Pin | Behavior |
|---|---|---|
| Fan | Uno D2 | HIGH on, LOW off; on/off only |
| Red LED | Uno D5 | Inverted PWM |
| Green LED | Uno D6 | Inverted PWM |
| Blue LED | Uno D9 | Inverted PWM |
| Pump | Uno D8 | HIGH on through a direct IRLZ44NPbF low-side gate |
| DHT11 | Pi GPIO4 / physical pin 7 | Pi reader; not an Arduino sensor |

The pump circuit assumes a common ground, source connected to ground, drain to
pump negative, and pump positive to its external supply. Use a gate resistor,
a gate-to-source pulldown, and a flyback diode across the pump. Motor power does
not come from GPIO. RGB polarity follows the original inverted-PWM wiring.
The UI hides fan speed controls and disables the unused white LED slider. Make
white with equal RGB values if desired.

`PUMP_ON` stops after at most 30 seconds. `PUMP_5S` runs for 5 seconds. Repeated ON
commands do not extend a running pump's maximum duration. All outputs start off
and turn off after 10 seconds without valid serial commands. The Pi's reader
sends STATUS heartbeats even if the browser is closed.

## Install on a matching Pi

Use Raspberry Pi OS with a desktop, labwc/Wayland, and the supported camera
packages. The supplied boot templates use account `germ`; either use that
account or replace `/home/germ` and `User=germ` in the templates for your account.
The HMI does not depend on the original Pi's IP address or SSH keys.

```sh
git clone https://github.com/turtle-robotics/GERM.git
mkdir -p /home/germ/hmi_flask
cp -a GERM/pi_hmi/. /home/germ/hmi_flask/
cd /home/germ/hmi_flask
sudo apt update
sudo apt install python3-venv python3-picamera2 python3-libcamera \
  python3-opencv libgpiod3 chromium curl wlr-randr
python3 -m venv --system-site-packages venv
venv/bin/python -m pip install -r requirements.txt
sudo usermod -aG dialout,video,gpio,i2c,spi,render germ
sudo install -d -o germ -g germ /var/lib/germ/images
```

Log out and back in after changing group membership. The virtual environment
must inherit system packages so it can import libcamera and Picamera2. The
requirements file pins the direct app dependencies observed on the Pi; apt
provides the camera stack. Package availability and drivers must match your OS
and hardware; the source export is not a complete OS image.

Install Arduino CLI at `/usr/local/bin/arduino-cli` using the official
[installation instructions](https://docs.arduino.cc/arduino-cli/installation/).
The exported Pi uses CLI 1.4.1 and AVR core 1.8.7. Then, as the HMI account:

```sh
/usr/local/bin/arduino-cli core update-index
/usr/local/bin/arduino-cli core install arduino:avr@1.8.7
```

The Uno controller sketch has no third-party Arduino library dependencies.
You can compile it before connecting hardware:

```sh
/usr/local/bin/arduino-cli compile --fqbn arduino:avr:uno arduino_program
```

## Boot service and kiosk

`deploy/hmi.service` is the existing Pi's service configuration. After adjusting
its account/paths if needed, install it:

```sh
sudo install -m 644 deploy/hmi.service /etc/systemd/system/hmi.service
sudo systemctl daemon-reload
sudo systemctl enable --now hmi.service
```

Open `http://127.0.0.1:5000` on the Pi. For the existing kiosk behavior:

```sh
install -m 755 deploy/start_hmi_browser.sh /home/germ/start_hmi_browser.sh
mkdir -p /home/germ/.config/labwc
# Merge with an existing autostart file instead of overwriting other startup commands.
cat deploy/labwc-autostart
```

Add those autostart lines to `~/.config/labwc/autostart`. They wait five seconds,
launch the browser script, and rotate output `DSI-1` by 180 degrees. Change or
omit the `wlr-randr` line if your display has a different output name or orientation.
Configure desktop autologin for the kiosk account through your Pi OS settings;
these source files do not include authentication or OS login configuration.
The existing interface was designed for a 739 × 447 kiosk viewport.

## Arduino control and firmware updates

The serial bridge auto-selects `/dev/ttyUSB*` or `/dev/ttyACM*`. For an explicit
port, add `Environment=GERM_SERIAL_PORT=/dev/ttyUSB0` to the service's `[Service]`
section or a systemd override. Arduino CLI defaults to `/usr/local/bin/arduino-cli`;
`GERM_ARDUINO_CLI` can override that path. Upload subprocesses add normal system
paths without changing the original service's virtual-environment PATH.

Open **Controls → Lighting**, choose **Normal HMI control** or **Rainbow**,
and press **Upload selected mode** to compile and flash that mode on the Uno.
The same selector is available under **Settings → Update Arduino firmware**. Compilation completes before USB is released.
The bridge then stops outputs, closes serial, flashes, and reconnects to verify
protocol 2. Do not run a separate Arduino Serial Monitor at the same time.
Single-file custom sketches can be uploaded through the same page; they must
implement protocol 2 to work with the HMI controls. Multi-file projects require
Arduino IDE/CLI.

Both modes use identical pins and inverted RGB PWM. Rainbow advances one hue
degree every 20 ms without blocking fan, pump, or serial commands. Fan and pump
remain under HMI control; uploading turns them off. **Apply** switches lighting
to manual RGB, and **Off** stops the animation. The selected upload mode is the
startup default after a reset; serial timeout or STOP still turns all outputs off.
The standalone root showcase sketch is the same controller with rainbow as its
startup default; it requires the Pi heartbeat for continuous operation.
The DHT11 remains on Pi GPIO4; neither current sketch needs an Arduino DHT library.

Firmware also accepts `MODE:normal` and `MODE:rainbow`, and reports
`lighting_mode` alongside RGB values. The HMI preserves the existing command names: `LED:r,g,b,w` (W must be zero),
`FAN_ON`, `FAN_OFF`, `PUMP_ON`, `PUMP_OFF`, and `PUMP_5S`. The bridge wraps them
as `CMD:<id>:<command>`, and firmware returns JSON containing the matching ID,
protocol version, output settings, and any error. `STATUS` polls output settings;
`STOP` turns all outputs off. Fan speed values other than 0/255 are rejected
because Uno D2 is not a PWM pin. A0 is reported unavailable until an actual
sensor and acquisition protocol are defined.

## Verify and troubleshoot

```sh
venv/bin/python check_integration.py
g++ -std=c++11 tests/firmware_behavior.cpp -o /tmp/germ-firmware-test
/tmp/germ-firmware-test
sudo systemctl status hmi.service
curl http://127.0.0.1:5000/api/state
journalctl -u hmi.service -n 50 --no-pager
```

`check_integration.py` runs ten checks with hardware and background workers
stubbed. `verify_live.py` checks the running HTTP endpoints and sends only fan
OFF, pump OFF, and LEDs OFF; it requires compatible firmware and a connected Uno.
The application compiles for the Uno, and those live OFF commands were confirmed
by the deployed firmware. Physical motor motion and LED appearance have not
been observed in these software checks.

Only one process may own the camera or USB serial port. Stop `hmi.service`
before running `venv/bin/python app.py` manually or testing the camera with
`rpicam-still -n -o /tmp/camera-test.jpg`, then restart the service afterwards.
`deploy_to_pi.py` is a developer staging helper with fixed paths; ordinary fresh
installation uses the steps above.

The exported `INTEGRATION.md` describes the SQL/ML handoff. Its historical status
notes predate the protocol-2 controller; this README describes the current
serial integration. `docs/PI_README_ORIGINAL.md` preserves the Pi's earlier
README as historical context.

## Publication and access

See [SECURITY.md](SECURITY.md) for the credential review and network-access
limits. Use the HMI on a trusted local network. It has no login system and
must not be exposed directly to the public Internet. Credentials, private SSH
notes, virtual environments, backups, archives, logs, captured data, and local
databases are excluded from Git. A source export reproduces application behavior;
it does not clone the Pi's OS, accounts, attached devices, or private data.
