Vous pouvez installer uv en suivant: https://docs.astral.sh/uv/getting-started/installation/

Pour installer picamera2 sous uv, vous devrez exécuter les commandes suivantes avant de démarrer uv run:
    sudo apt update && sudo apt upgrade
    sudo apt install libcap-dev libatlas-base-dev ffmpeg libopenjp2-7
    sudo apt install libcamera-dev
    sudo apt install libkms++-dev libfmt-dev libdrm-dev

Ensuite, dans le répertoire cloné sur votre machine:
    uv pip install wheel
    uv pip install rpi-libcamera rpi-kms picamera2

Vous aurez aussi besoin de lgpio:
    sudo apt install swig
    sudo apt install liblgpio-dev
