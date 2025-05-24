"""
Service WebSocket pour la communication temps réel.
Optimisé pour une latence minimale avec mise à jour à haute fréquence.
"""

import asyncio
import json
import logging
import time
from typing import Any, Optional

import websockets
from config import config
from core.camera_service import camera_service
from core.joystick_service import joystick_service
from core.robot_service import robot_service
from websockets.server import WebSocketServerProtocol


class WebSocketServer:
    """Serveur WebSocket pour communication temps réel"""
    
    def __init__(self):
        self.server: Optional[websockets.WebSocketServer] = None
        self.clients: set[WebSocketServerProtocol] = set()
        self.is_running = False
        self.logger = logging.getLogger(__name__)
        
        # Fréquence d'envoi des mises à jour
        self.update_frequency = config.web.websocket_frequency
        self.update_interval = 1.0 / self.update_frequency
        
        # Dernières données envoyées pour éviter les doublons
        self.last_state = {}
        self.last_update_time = 0.0
        
        # Configuration des callbacks
        self._setup_service_callbacks()
    
    def _setup_service_callbacks(self):
        """Configure les callbacks des services pour les mises à jour temps réel"""
        
        # Callback pour les changements d'état du robot
        robot_service.add_state_callback(self._on_robot_state_change)
        
        # Callback pour les changements d'état de la manette
        joystick_service.add_state_callback(self._on_joystick_state_change)
        
        # Callback pour les nouvelles frames de caméra (optionnel)
        # camera_service.add_frame_callback(self._on_new_frame)
    
    def _on_robot_state_change(self, state: dict[str, Any]):
        """Callback appelé lors des changements d'état du robot"""
        self._broadcast_message({
            "type": "robot_state",
            "data": state,
            "timestamp": time.time()
        })
    
    def _on_joystick_state_change(self, state: dict[str, Any]):
        """Callback appelé lors des changements d'état de la manette"""
        # Évite d'envoyer trop de messages pour les axes
        current_time = time.time()
        if current_time - self.last_update_time < self.update_interval:
            return
        
        self._broadcast_message({
            "type": "joystick_state",
            "data": state,
            "timestamp": current_time
        })
        
        self.last_update_time = current_time
    
    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Gestionnaire pour les connexions client WebSocket"""
        client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self.logger.info(f"Nouvelle connexion WebSocket: {client_addr}")
        
        # Ajoute le client
        self.clients.add(websocket)
        
        try:
            # Envoie l'état initial
            await self._send_initial_state(websocket)
            
            # Boucle de traitement des messages
            async for message in websocket:
                await self._handle_message(websocket, message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Connexion fermée: {client_addr}")
        except Exception as e:
            self.logger.error(f"Erreur avec le client {client_addr}: {e}")
        finally:
            # Supprime le client
            self.clients.discard(websocket)
    
    async def _send_initial_state(self, websocket: WebSocketServerProtocol):
        """Envoie l'état initial au client"""
        try:
            initial_state = {
                "type": "initial_state",
                "data": {
                    "robot": robot_service.get_state(),
                    "camera": camera_service.get_stats(),
                    "joystick": joystick_service.get_state()
                },
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(initial_state))
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de l'état initial: {e}")
    
    async def _handle_message(self, websocket: WebSocketServerProtocol, message: str):
        """Traite un message reçu du client"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            payload = data.get("data", {})
            
            # Traite selon le type de message
            if message_type == "robot_command":
                await self._handle_robot_command(websocket, payload)
            elif message_type == "robot_joystick":
                await self._handle_joystick_command(websocket, payload)
            elif message_type == "emergency_stop":
                await self._handle_emergency_stop(websocket)
            elif message_type == "get_status":
                await self._handle_status_request(websocket)
            else:
                await self._send_error(websocket, f"Type de message inconnu: {message_type}")
                
        except json.JSONDecodeError:
            await self._send_error(websocket, "Message JSON invalide")
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du message: {e}")
            await self._send_error(websocket, str(e))
    
    async def _handle_robot_command(self, websocket: WebSocketServerProtocol, payload: dict[str, Any]):
        """Traite une commande robot"""
        command = payload.get("command")
        speed = payload.get("speed")
        
        if not command:
            await self._send_error(websocket, "Commande requise")
            return
        
        success = robot_service.execute_command(command, speed)
        
        await websocket.send(json.dumps({
            "type": "command_result",
            "success": success,
            "command": command,
            "timestamp": time.time()
        }))
    
    async def _handle_joystick_command(self, websocket: WebSocketServerProtocol, payload: dict[str, Any]):
        """Traite une commande de manette virtuelle"""
        axis_x = payload.get("axis_x", 0.0)
        axis_y = payload.get("axis_y", 0.0)
        
        success = robot_service.move_with_joystick(axis_x, axis_y)
        
        # Pas besoin de réponse pour les commandes joystick (haute fréquence)
        if not success:
            await self._send_error(websocket, "Échec de la commande joystick")
    
    async def _handle_emergency_stop(self, websocket: WebSocketServerProtocol):
        """Traite un arrêt d'urgence"""
        success = robot_service.emergency_stop()
        
        await websocket.send(json.dumps({
            "type": "emergency_stop_result",
            "success": success,
            "timestamp": time.time()
        }))
    
    async def _handle_status_request(self, websocket: WebSocketServerProtocol):
        """Traite une demande de statut"""
        status = {
            "robot": robot_service.get_state(),
            "camera": camera_service.get_stats(),
            "joystick": joystick_service.get_state()
        }
        
        await websocket.send(json.dumps({
            "type": "status",
            "data": status,
            "timestamp": time.time()
        }))
    
    async def _send_error(self, websocket: WebSocketServerProtocol, error: str):
        """Envoie un message d'erreur"""
        await websocket.send(json.dumps({
            "type": "error",
            "error": error,
            "timestamp": time.time()
        }))
    
    def _broadcast_message(self, message: dict[str, Any]):
        """Diffuse un message à tous les clients connectés"""
        if not self.clients:
            return
        
        message_str = json.dumps(message)
        
        # Envoie de manière asynchrone
        asyncio.create_task(self._send_to_all_clients(message_str))
    
    async def _send_to_all_clients(self, message: str):
        """Envoie un message à tous les clients (coroutine)"""
        if not self.clients:
            return
        
        # Copie la liste des clients pour éviter les modifications concurrentes
        clients = self.clients.copy()
        
        # Envoie à tous les clients en parallèle
        tasks = []
        for client in clients:
            task = asyncio.create_task(self._safe_send(client, message))
            tasks.append(task)
        
        # Attend que tous les envois se terminent
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send(self, websocket: WebSocketServerProtocol, message: str):
        """Envoie un message de manière sécurisée"""
        try:
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            # Client déconnecté, supprime de la liste
            self.clients.discard(websocket)
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi à un client: {e}")
            self.clients.discard(websocket)
    
    async def start(self) -> bool:
        """Démarre le serveur WebSocket"""
        if self.is_running:
            self.logger.warning("Serveur WebSocket déjà en cours")
            return True
        
        try:
            self.server = await websockets.serve(
                self._handle_client,
                config.web.host,
                config.web.websocket_port,
                ping_interval=20,  # Garde les connexions actives
                ping_timeout=10,
                max_size=None,  # Pas de limite de taille
                compression=None  # Pas de compression pour la vitesse
            )
            
            self.is_running = True
            self.logger.info(f"Serveur WebSocket démarré sur ws://{config.web.host}:{config.web.websocket_port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage du serveur WebSocket: {e}")
            return False
    
    async def stop(self):
        """Arrête le serveur WebSocket"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        # Ferme toutes les connexions client
        if self.clients:
            await asyncio.gather(
                *[client.close() for client in self.clients],
                return_exceptions=True
            )
            self.clients.clear()
        
        self.logger.info("Serveur WebSocket arrêté")
    
    def get_client_count(self) -> int:
        """Retourne le nombre de clients connectés"""
        return len(self.clients)


# Instance globale du serveur WebSocket
websocket_server = WebSocketServer()
