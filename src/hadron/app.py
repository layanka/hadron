from pickletools import optimize
import threading
import time
from typing import List

import libcamera
import uvicorn
from carController import RobotCar
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from joystickController import JoystickReader
from libcamera import controls
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from streamOutput import StreamingOutput

# Initialisation de FastAPI
app = FastAPI()

# Modifier le chemin des fichiers statiques pour utiliser un chemin absolu
import os
static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Utiliser le même principe pour les templates
templates_path = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_path)

##
# Our robot instance.
# If the iC2 from the Adafruit board is not ready, the server will still start
#   but the robot won't move.
# Basically, just the camera will work.
##
robot = RobotCar()
if robot._dummy:
    print("Adafruit MotorHat not found. Running in dummy mode.")



##
# Create a joystick instance, configure it
# Define how it's going to work (you can modify it as you please,
#   ex: a button for speed change, etc.)
# And start monitoring it in a sepearet thread.
##
joystick = JoystickReader("/dev/input/js0")
joystick_speed = 0.0
joystick_steering = 0.0
joystick_active = True  # Deactivate joystick control if you don't want it



# Déplacer la configuration de la caméra dans une classe
class CameraManager:
    def __init__(self):
        self.picam2 = None
        self.output = None
        self.jpeg_encoder = None

    def setup_camera(self):
        if self.picam2 is not None:
            return

        self.picam2 = Picamera2()
        config = self.picam2.create_video_configuration(
            main={
                "size": (320, 240),
                "format": "RGB888"
            },
            buffer_count=4,
            controls={
                "FrameRate": 15.0,
                "FrameDurationLimits": (66666, 66666),
                "AfMode": controls.AfModeEnum.Continuous,
                "NoiseReductionMode": controls.draft.NoiseReductionModeEnum.Minimal,
                "Brightness": 0.5,
                "Contrast": 1.1,
            }
        )
        config["transform"] = libcamera.Transform(hflip=1, vflip=1)
        self.picam2.configure(config)
        self.output = StreamingOutput()
        
        self.jpeg_encoder = JpegEncoder(q=70)
        
        self.picam2.start_recording(
            encoder=self.jpeg_encoder,
            output=FileOutput(self.output)
        )

    def cleanup(self):
        if self.picam2:
            try:
                self.picam2.stop_recording()
                self.picam2.close()
            except:
                pass

# Créer une instance unique
camera_manager = CameraManager()

@app.on_event("startup")
async def startup_event():
    """Initialisation à l'startup de l'application."""
    camera_manager.setup_camera()

@app.on_event("shutdown")
async def shutdown_event():
    """Nettoyage à l'arrêt de l'application."""
    camera_manager.cleanup()

def joystick_control():
    global joystick_speed, joystick_steering, joystick_active
    try:
        for event in joystick.read_events():
            if not joystick_active:
                continue

            if event["type"] == 2:  # Axis (type 2)
                if event["number"] == 2:  # Axis 2 (steering left/right)
                    joystick_steering = event["value"] / 32767.0  # Normalize to [-1, 1]
                elif event["number"] == 3:  # Axis 3 (speed forward/backward)
                    joystick_speed = event["value"] / 32767.0  # Normalize to [-1, 1]

            # Send command to robot
            robot.steer(joystick_speed, joystick_steering)

            # To make sure we don,t overload the CPU
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Joystick control stopped.")
        robot.stop()


# Read the joystick in a sperate thread
joystick_thread = threading.Thread(target=joystick_control, daemon=True)
joystick_thread.start()
# joystick_thread.join()


# Modifier generate_videostream pour utiliser camera_manager
def generate_videostream():
    try:
        while True:
            with camera_manager.output.condition:
                if not camera_manager.output.condition.wait(timeout=2.0):
                    continue
                frame = camera_manager.output.frame
                if frame is None:
                    continue
                
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + f"{len(frame)}".encode() + b"\r\n"
                b"\r\n" + frame + b"\r\n"
            )
    except Exception as e:
        print(f"Erreur de streaming: {e}")
        camera_manager.cleanup()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        generate_videostream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/command/{cmd}")
async def command(cmd: str):
    speed = 0.5
    if cmd == "forward":
        robot.forward(speed)
        return {"message": "Action en cours: Avancer"}
    elif cmd == "backward":
        robot.backward(speed)
        return {"message": "Action en cours: Reculer"}
    elif cmd == "left":
        robot.left(speed)
        return {"message": "Action en cours: Tourner à gauche"}
    elif cmd == "right":
        robot.right(speed)
        return {"message": "Action en cours: Tourner à droite"}
    elif cmd == "stop":
        robot.stop()
        return {"message": "Action en cours: À l'arrêt"}
    return {"message": "Commande inconnue"}


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Envoi du statut
            await websocket.send_json({
                "connected": not robot._dummy,
                "speed": joystick_speed,
                "steering": joystick_steering
            })
            
            # Réception des commandes
            data = await websocket.receive_json()
            if "command" in data:
                cmd = data["command"]
                value = data.get("value", 0.5)
                
                if cmd == "steer":
                    speed = data.get("speed", 0.3)
                    direction = data.get("direction", 0)
                    robot.steer(speed, direction)
                elif cmd in ["forward", "backward", "left", "right"]:
                    getattr(robot, cmd)(value)
                elif cmd == "stop":
                    robot.stop()
                
                await websocket.send_json({
                    "status": "ok",
                    "command": cmd,
                    "value": value
                })
    except Exception as e:
        print(f"WebSocket error: {e}")
        robot.stop()
    finally:
        manager.disconnect(websocket)


import gc

def cleanup_resources():
    """Nettoie les ressources système."""
    try:
        picam2.stop_recording()
        picam2.close()
        gc.collect()  # Force la collecte des déchets
    except:
        pass

# Ajoutez ceci à la fin du fichier
import atexit
atexit.register(cleanup_resources)


# Modifier le démarrage pour n'utiliser qu'un seul worker
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        workers=1,  # Réduit à 1 worker
        loop="uvloop"
    )
