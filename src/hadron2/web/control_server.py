"""
Service de contrôle web pour les commandes du robot.
Interface REST FastAPI haute performance.
"""

import asyncio
import logging
import threading

import uvicorn
from config import config
from core.robot_service import robot_service
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# Modèles Pydantic pour validation automatique
class RobotCommand(BaseModel):
    command: str
    value: float = 0.5

class JoystickCommand(BaseModel):
    axis_x: float = 0.0
    axis_y: float = 0.0

class RobotResponse(BaseModel):
    status: str
    command: str
    value: float
    is_moving: bool
    is_connected: bool


class ControlServerFastAPI:
    """Serveur de contrôle REST FastAPI pour le robot"""
    
    def __init__(self):
        self.app = FastAPI(
            title="Robot Control API",
            description="API de contrôle haute performance pour robot Hadron",
            version="2.0.0"
        )
        self.server_thread: threading.Thread | None = None
        self.server: uvicorn.Server | None = None
        self.is_running = False
        self.logger = logging.getLogger(__name__)
        
        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=config.web.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Configure les routes FastAPI du serveur de contrôle"""
        
        @self.app.post("/api/robot/command", response_model=RobotResponse)
        async def robot_command(cmd: RobotCommand):
            """Exécute une commande robot avec validation Pydantic"""
            try:
                success = robot_service.execute_command(cmd.command, cmd.value)
                state = robot_service.get_state()
                
                return RobotResponse(
                    status="success" if success else "error",
                    command=state["command"],
                    value=cmd.value,
                    is_moving=state["is_moving"],
                    is_connected=state["is_connected"]
                )
            except Exception as e:
                self.logger.error(f"Erreur commande robot: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e
        
        @self.app.post("/api/robot/joystick")
        async def joystick_command(joy: JoystickCommand):
            """Commandes joystick avec validation"""
            try:
                # Validation des valeurs d'axes
                if not (-1.0 <= joy.axis_x <= 1.0) or not (-1.0 <= joy.axis_y <= 1.0):
                    raise HTTPException(
                        status_code=400, 
                        detail="Les valeurs d'axes doivent être entre -1.0 et 1.0"
                    )
                
                success = robot_service.move_with_joystick(joy.axis_x, joy.axis_y)
                state = robot_service.get_state()
                
                return {
                    "status": "success" if success else "error",
                    "axis_x": joy.axis_x,
                    "axis_y": joy.axis_y,
                    "is_moving": state["is_moving"],
                    "is_connected": state["is_connected"]
                }
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Erreur commande joystick: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e
        
        @self.app.post("/api/robot/emergency_stop")
        async def emergency_stop():
            """Arrêt d'urgence"""
            try:
                success = robot_service.emergency_stop()
                return {"status": "success" if success else "error"}
            except Exception as e:
                self.logger.error(f"Erreur arrêt d'urgence: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e
        
        @self.app.get("/api/status")
        async def status():
            """Statut global du système"""
            try:
                state = robot_service.get_state()
                return {
                    "robot": state,
                    "available": robot_service.is_available()
                }
            except Exception as e:
                self.logger.error(f"Erreur dans la récupération du statut: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e
        
        @self.app.get("/api/health")
        async def health():
            """Health check pour monitoring"""
            try:
                robot_available = robot_service.is_available()
                robot_status = "operational" if robot_available else "error"
                return {
                    "status": "healthy",
                    "robot_available": robot_available,
                    "services": {
                        "robot": robot_status
                    }
                }
            except Exception as e:
                self.logger.error(f"Erreur health check: {e}")
                return JSONResponse(
                    status_code=503,
                    content={"status": "unhealthy", "error": str(e)}
                )
    
    async def start(self) -> bool:
        """Démarre le serveur de contrôle FastAPI"""
        if self.is_running:
            self.logger.warning("Le serveur de contrôle est déjà en cours d'exécution")
            return True
        
        try:
            def run_server():
                config_uvicorn = uvicorn.Config(
                    app=self.app,
                    host=config.web.host,
                    port=config.web.port,
                    log_level="info",
                    access_log=False  # Réduit les logs pour la performance
                )
                self.server = uvicorn.Server(config_uvicorn)
                asyncio.run(self.server.serve())
        
            self.server_thread = threading.Thread(target=run_server, daemon=True)
            self.is_running = True
            self.server_thread.start()
            host = config.web.host
            port = config.web.port
            msg = f"Serveur de contrôle FastAPI démarré sur {host}:{port}"
            self.logger.info(msg)
            return True
        except Exception as e:
            self.logger.error(f"Erreur démarrage serveur de contrôle: {e}")
            return False
    
    def stop(self):
        """Arrête le serveur de contrôle"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.server:
            self.server.should_exit = True
        
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
        
        self.logger.info("Serveur de contrôle FastAPI arrêté")


# Instance globale
control_server = ControlServerFastAPI()
