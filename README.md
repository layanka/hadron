# Hadron

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

Restart your RaspberryPi and upon turning on your controller, the Flask server will automatically start.
Note: The server starts and we can control the robot by joystick, however, the website is not accessible. To be verified.
