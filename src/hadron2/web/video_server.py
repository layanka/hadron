"""
Service de serveur vidéo pour le streaming de la caméra.
Optimisé pour une latence minimale avec MJPEG streaming.
"""

import logging
import threading

import uvicorn
from config import config
from core.camera_service import camera_service
from fastapi import FastAPI
from fastapi.responses import StreamingResponse


class VideoServer:
    """Serveur de streaming vidéo MJPEG haute performance avec FastAPI"""
    
    def __init__(self):
        self.app = FastAPI(
            title="Video Streaming API",
            description="API de streaming vidéo haute performance",
            version="2.0.0"
        )
        self.server_thread: threading.Thread | None = None
        self.server: uvicorn.Server | None = None
        self.is_running = False
        self.logger = logging.getLogger(__name__)
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Configure les routes du serveur vidéo"""
        
        @self.app.get("/video_feed")
        async def video_feed():
            """Route principale pour le flux vidéo MJPEG"""
            return StreamingResponse(
                self._generate_frames(),
                media_type="multipart/x-mixed-replace; boundary=frame"
            )
        
        @self.app.get("/video_stats")
        async def video_stats():
            """Route pour les statistiques vidéo"""
            return camera_service.get_stats()
        
        @self.app.get("/health")
        async def health():
            """Route de vérification de santé"""
            return {
                "status": "healthy" if camera_service.is_available() else "unhealthy",
                "camera_available": camera_service.is_available(),
                "is_streaming": self.is_running
            }
    
    def _generate_frames(self):
        """Générateur de frames pour le streaming MJPEG"""
        for frame_data in camera_service.frame_generator():
            if not self.is_running:
                break
            
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n")
    
    def start(self) -> bool:
        """Démarre le serveur vidéo FastAPI"""
        if self.is_running:
            self.logger.warning("Serveur vidéo déjà en cours")
            return True
        
        try:
            # Démarre la capture si nécessaire
            if not camera_service.start_capture():
                self.logger.error("Impossible de démarrer la capture vidéo")
                return False
            
            # Configuration du serveur uvicorn
            uvicorn_config = uvicorn.Config(
                app=self.app,
                host=config.web.host,
                port=config.web.video_port,
                log_level="error",  # Réduire les logs pour les performances
                access_log=False
            )
            
            self.server = uvicorn.Server(uvicorn_config)
            self.is_running = True
            
            # Lance le serveur dans un thread séparé
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self.server_thread.start()
            
            host = config.web.host
            port = config.web.video_port
            self.logger.info(f"Serveur vidéo FastAPI démarré sur {host}:{port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage du serveur vidéo: {e}")
            self.is_running = False
            return False
    
    def _run_server(self):
        """Lance le serveur uvicorn"""
        try:
            if self.server:
                import asyncio
                asyncio.run(self.server.serve())
        except Exception as e:
            self.logger.error(f"Erreur du serveur vidéo: {e}")
        finally:
            self.is_running = False
    
    def stop(self):
        """Arrête le serveur vidéo"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.server:
            self.server.should_exit = True
        
        self.logger.info("Serveur vidéo arrêté")
    
    def get_stream_url(self) -> str:
        """Retourne l'URL du flux vidéo"""
        return f"http://{config.web.host}:{config.web.video_port}/video_feed"


# Instance globale du serveur vidéo
video_server = VideoServer()
