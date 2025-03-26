# Hadron
The goal is to build a robot with more and more capabilities.

At this point (March 2025), the robot:
  - Is programmed with Python
  - Can be controlled through a web page (Flask server) which allows to control it via buttons on the web page, your keyboard or a bluetooth game controller.
  - Streams live video on the web page

#### For hardware, it is based on:

Raspberry Pi 5 (wil work with other versions) : https://www.raspberrypi.com/products/raspberry-pi-5/
  - I think that other versions would work better for portable solution
    
(still unused so far) Raspberry Pi AI Kit (will work with the Raspberry Pi AI HAT+) : https://www.raspberrypi.com/products/ai-kit/
  - I plan to leverage this but a lot (most) of AI solutions can still be implemented without a dedicated AI module.
    
Raspberry Pi Camera Module 3 : https://www.raspberrypi.com/products/camera-module-3/
  - Other cameras can be used, code might need tweeking

Adafruit crickit HAT: https://www.adafruit.com/product/3957
  - The Motor Hat might be sufficient if you don't use the other capabilities of the Crickit

For mobility:
- Mini Robot Rover Chassis Kit (you'll need extra spacers if you have the AI Kit as well)
- A simple 4xAA holder (similar to https://www.adafruit.com/product/830) to power the Crickit
- A power bank to power the Raspberry Pi. hard to find a good one for the Pi 5. This one works: https://www.amazon.ca/-/fr/dp/B0DD3JZ1QR?ref=ppx_yo2ov_dt_b_fed_asin_title&th=1. Look for something small, with at least one output of 25W+. The Pi 5 needs 5V and 3A, I have not found any that fits the bill perfectly, aside from dedicated solutions in the type a UPS with extension circuit board which might be what you're looking for if you're looking for a robust solution.

Note that nothing fits perfectly here: Staking 3 boards requires extra parts (pin extensions, etc.), the Rover Kit was not meant for the Pi 5 originally and not for 3 boards, you will need to strip some wires, etc.



## Getting Started

You can install `uv` by following: [installation instructions](https://docs.astral.sh/uv/getting-started/installation/)

To install `picamera2` under `uv`, you will need to run the following commands before starting `uv run`:

```bash
sudo apt update && sudo apt upgrade
sudo apt install libcap-dev libatlas-base-dev ffmpeg libopenjp2-7
sudo apt install libcamera-dev
sudo apt install libkms++-dev libfmt-dev libdrm-dev
```

Then, in the cloned directory on your machine:

```bash
uv pip install wheel
uv pip install rpi-libcamera rpi-kms picamera2
```

You will also need `lgpio`:

```bash
sudo apt install swig
sudo apt install liblgpio-dev
```

You can then start the Flask server:

```bash
uv run src/hadron/app.py
```

## Miscellaneous

### Automatic server start at the connection of a game controller

You can use `udev` to automatically start the Flask server when a game controller connection is established.

Create a script that starts your server:

```bash
cd ~/.local/bin/
nano trigger_bot_on_joystick.sh
sudo chmod +x trigger_bot_on_joystick.sh
```

Add the following lines to the new file:

```bash
cd /home/USERNAME/PATH_TO_PROJECTDIR
uv run src/hadron/app.py
```

Create a link in `/usr/local/bin/`:

```bash
cd /usr/local/bin
sudo ln ~/.local/bin/trigger_bot_on_joystick.sh
```

Create or add the following line to `/etc/udev/rules.d/80-local.rules`:

```bash
KERNEL=="js0", SUBSYSTEM=="input", ACTION=="add", RUN+="/usr/local/bin/trigger_bot_on_joystick.sh"
```

Finally, if `sudo uv` does not work, create a link:

```bash
cd /usr/local/bin
sudo ln ~/.local/bin/uv uv
```

Restart your Raspberry Pi and upon turning on your controller, the Flask server will automatically start.
Note: The server starts and we can control the robot by joystick, however, the website is not accessible. To be verified.
