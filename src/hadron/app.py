from flask import Flask, Response, render_template
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import libcamera
from libcamera import controls
from streamOutput import StreamingOutput
from carController import RobotCar
from joystickController import JoystickReader
import threading
import time

app = Flask(__name__)

# Configure and start the camera stream
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (320, 240)}
)  # Réduire à 320x240
config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(config)
picam2.set_controls({"FrameRate": 15.0})  # Limiter à 15 FPS
picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))

robot = RobotCar()
if (robot._dummy):
    print("Adafruit MotorHat not found. Running in dummy mode.")
joystick = JoystickReader("/dev/input/js0")

# Variables globales pour le joystick
joystick_speed = 0.0
joystick_steering = 0.0
joystick_active = True  # Permet d'activer/désactiver le contrôle par joystick


def joystick_control():
    global joystick_speed, joystick_steering, joystick_active
    try:
        for event in joystick.read_events():
            if not joystick_active:
                continue

            if event["type"] == 2:  # Axes (type 2)
                if event["number"] == 2:  # Axis 2 (steering left/right)
                    joystick_steering = event["value"] / 32767.0  # Normaliser [-1, 1]
                elif event["number"] == 3:  # Axis 3 (speed forward/backward)
                    joystick_speed = event["value"] / 32767.0  # Normaliser [-1, 1]

            # Appliquer les commandes au robot
            robot.steer(joystick_speed, joystick_steering)

            # Petite pause pour éviter une surcharge CPU
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Joystick control stopped.")
        robot.stop()


# Lancer le contrôle par joystick dans un thread séparé
joystick_thread = threading.Thread(target=joystick_control, daemon=True)
joystick_thread.start()
# joystick_thread.join()


def generate_videostream():
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_videostream(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/")
def index():
    return render_template("index.html")    


@app.route("/command/<cmd>")
def command(cmd):
    speed = 0.5
    if cmd == "forward":
        robot.forward(speed)
        return "Action en cours: Avancer"
    elif cmd == "backward":
        robot.backward(speed)
        return "Action en cours: Reculer"
    elif cmd == "left":
        robot.left(speed)
        return "Action en cours: Tourner à gauche"
    elif cmd == "right":
        robot.right(speed)
        return "Action en cours: Tourner à droite"
    elif cmd == "stop":
        robot.stop()
        return "Action en cours: À l'arrêt"
    else:
        return "???"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
