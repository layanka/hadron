import asyncio
import base64
import json
import time
from collections import deque
from typing import List, Optional

import cv2
import numpy as np
import websockets
from fastmcp import FastMCPServer, Tool
from fastmcp.types import TextContent

ROBOT_HOST = "192.168.0.157"
ROBOT_PORT = 5000

class HadronMCPServer(FastMCPServer):
    def __init__(self):
        super().__init__(
            name="robot-controller",
            version="2.0.0"
        )
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.robot_status = {"connected": False, "status": "unknown"}
        self.last_command_time = 0
        self.command_throttle = 0.05  # 50ms minimum entre les commandes
        self.last_status = {}
        self.command_queue = asyncio.Queue(maxsize=10)
        self.setup_handlers()
        asyncio.create_task(self._process_command_queue())
        self.frame_cache = deque(maxlen=5)  # Cache des 5 dernières images
        self.last_frame_time = 0
        self.frame_throttle = 0.033  # ~30 FPS

    async def start_services(self):
        """Établit une connexion WebSocket optimisée."""
        try:
            self.ws_connection = await websockets.connect(
                f"ws://{ROBOT_HOST}:{ROBOT_PORT}/ws",
                ping_interval=0.5,  # Réduit à 500ms
                ping_timeout=2,     # Timeout plus court
                max_size=None,      # Pas de limite de taille
                compression=None    # Désactive la compression pour réduire la latence
            )
            self.robot_status["connected"] = True
            asyncio.create_task(self._heartbeat())
        except Exception as e:
            print(f"Erreur de connexion au robot: {e}")

    async def _heartbeat(self):
        """Maintient la connexion avec gestion d'état optimisée."""
        while True:
            try:
                if self.ws_connection:
                    await self.ws_connection.ping()
                    status = await self.ws_connection.recv()
                    new_status = json.loads(status)
                    
                    # Ne met à jour que si l'état a changé
                    if new_status != self.last_status:
                        self.robot_status = new_status
                        self.last_status = new_status.copy()
            except:
                if self.robot_status["connected"]:
                    self.robot_status["connected"] = False
                    self.last_status = {}
                await asyncio.sleep(1)
                await self.start_services()
            
            await asyncio.sleep(0.05)  # Réduit à 50ms pour plus de réactivité

    async def send_robot_command(self, command: dict) -> str:
        """Envoie une commande au robot avec throttling."""
        current_time = time.time()
        if current_time - self.last_command_time < self.command_throttle:
            await asyncio.sleep(self.command_throttle)
        
        if not self.ws_connection:
            raise Exception("Non connecté au robot")
        
        self.last_command_time = time.time()
        await self.ws_connection.send(json.dumps(command))
        response = await self.ws_connection.recv()
        return response

    async def _process_command_queue(self):
        """Traite la file d'attente des commandes."""
        while True:
            if self.ws_connection and not self.command_queue.empty():
                command = await self.command_queue.get()
                await self.send_robot_command(command)
            await asyncio.sleep(0.01)

    def setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            return [
                Tool(
                    name="control_robot",
                    description="Contrôle en temps réel du robot",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "enum": ["forward", "backward", "left", "right", "stop", "steer"]
                            },
                            "speed": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                            "direction": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                            "value": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                        },
                        "required": ["command"],
                        "allOf": [
                            {
                                "if": {"properties": {"command": {"const": "steer"}}},
                                "then": {"required": ["speed", "direction"]}
                            }
                        ]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> List[TextContent]:
            if name == "control_robot":
                try:
                    current_time = time.monotonic()
                    # Vérifie si le délai entre les commandes est respecté
                    if current_time - self.last_command_time < self.command_throttle:
                        raise Exception("Délai entre les commandes trop court")

                    # Pour la commande steer, on utilise speed et direction
                    if arguments["command"] == "steer":
                        command_data = {
                            "command": "steer",
                            "speed": arguments.get("speed", 0.0),
                            "direction": arguments.get("direction", 0.0)
                        }
                    else:
                        # Pour les autres commandes, on utilise value
                        command_data = {
                            "command": arguments["command"],
                            "value": arguments.get("value", 0.5)
                        }

                    result = await self.send_robot_command(command_data)
                    self.last_command_time = current_time
                    return [TextContent(type="text", text=result)]
                except Exception as e:
                    return [TextContent(type="text", text=f"Erreur: {str(e)}")]
        
        @self.server.call_tool()
        async def handle_get_video_frame(name: str, arguments: dict) -> Optional[bytes]:
            """Récupère une frame avec optimisation."""
            current_time = time.time()
            
            # Vérifier si une frame récente est disponible dans le cache
            if self.frame_cache and current_time - self.last_frame_time < self.frame_throttle:
                return self.frame_cache[-1]
                
            try:
                url = f"http://{ROBOT_HOST}:{ROBOT_PORT}/video_feed"
                async with self.http_client.stream('GET', url) as response:
                    async for chunk in response.aiter_bytes():
                        # Identifier le début et la fin d'une frame JPEG
                        if chunk.startswith(b'\xff\xd8') and chunk.endswith(b'\xff\xd9'):
                            # Compression et optimisation de l'image
                            img_array = np.frombuffer(chunk, dtype=np.uint8)
                            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                            
                            # Redimensionner si nécessaire
                            frame = cv2.resize(frame, (640, 480))
                            
                            # Compression JPEG optimisée
                            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                            _, buffer = cv2.imencode('.jpg', frame, encode_param)
                            
                            # Mise en cache
                            self.frame_cache.append(buffer.tobytes())
                            self.last_frame_time = current_time
                            
                            return buffer.tobytes()
                            
            except Exception as e:
                print(f"Erreur de capture vidéo: {e}")
                return None

        @self.server.call_tool()
        async def handle_video_frame() -> List[TextContent]:
            try:
                frame_data = await self.get_video_frame()
                if frame_data:
                    # Conversion en base64 pour transmission
                    frame_b64 = base64.b64encode(frame_data).decode('utf-8')
                    return [TextContent(
                        type="image",
                        text=f"data:image/jpeg;base64,{frame_b64}"
                    )]
            except Exception as e:
                return [TextContent(type="text", text=f"Erreur vidéo: {str(e)}")]