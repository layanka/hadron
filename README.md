Démarrage
---------------

Vous pouvez installer ``uv`` en suivant: https://docs.astral.sh/uv/getting-started/installation/

Pour installer ``picamera2`` sous ``uv``, vous devrez exécuter les commandes suivantes avant de démarrer ``uv run``:

    sudo apt update && sudo apt upgrade
    sudo apt install libcap-dev libatlas-base-dev ffmpeg libopenjp2-7
    sudo apt install libcamera-dev
    sudo apt install libkms++-dev libfmt-dev libdrm-dev

Ensuite, dans le répertoire cloné sur votre machine:

    uv pip install wheel
    uv pip install rpi-libcamera rpi-kms picamera2

Vous aurez aussi besoin de ``lgpio``:

    sudo apt install swig
    sudo apt install liblgpio-dev

Vous pourrez ensuite démarrer le serveur Flask:

    uv run src/hadron/mainRobot.py


Démarrage automatique du serveur à la connexion d'un controlleur de jeux
---------------

On peut utiliser ``udev`` pour démarrer automatiquement le serveur Flask quand une connection à un controlleur de jeux est établie.

Créez un script qui démarre votre serveur:

    cd ~/.local/bin/
    nano trigger_bot_on_joystick.sh
    sudo chmod +x trigger_bot_on_joystick.sh

Ajoutez les lignes suivantes au nouveau fichier:

    cd /home/USERNAME/PATH_TO_PROJECTDIR
    uv run src/hadron/mainRobot.py

Créez un lien dans ``/usr/local/bin/``:

    cd /usr/local/bin
    sudo ln ~/.local/bin/trigger_bot_on_joystick.sh

Créez ou ajouter la ligne suivante à ``/etc/udev/rules.d/80-local.rules``:

    KERNEL=="js0", SUBSYSTEM=="input", ACTION=="add", RUN+="/usr/local/bin/trigger_bot_on_joystick.sh"

Finalement, si ``sudo uv`` ne fonctionne pas, créez un lien:

    cd /usr/local/bin
    sudo ln ~/.local/bin/uv uv

Redémarrez votre RaspberryPi et en allumant votre controlleur, le serveur Flask démarrera automatiquement.