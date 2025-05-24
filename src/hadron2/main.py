"""
Application principale avec architecture modulaire.
Gestion centralisée de tous les services avec latence optimisée.
"""

import asyncio
import logging
import signal
import sys

# Configuration
from config import config, configure_for_development, configure_for_production
from core.camera_service import camera_service
from core.joystick_service import joystick_service

# Services principaux
from core.robot_service import robot_service

# Serveur MCP
from mcp_wrapper import mcp_server
from web.control_server import control_server  # Maintenant FastAPI

# Serveurs web
from web.video_server import video_server
from web.websocket_server import websocket_server


class Application:
    """Application principale gérant tous les services"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self._setup_logging()
        self._setup_signal_handlers()
        
        # Connecte la manette au robot
        self._setup_joystick_robot_connection()
    
    def _setup_logging(self):
        """Configure le système de logging"""
        logging.basicConfig(
            level=getattr(logging, config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                (logging.FileHandler("robot_app.log") 
                 if not config.debug else logging.NullHandler())
            ]
        )
    
    def _setup_signal_handlers(self):
        """Configure les gestionnaires de signaux pour un arrêt propre"""
        def signal_handler(signum, frame):
            self.logger.info(f"Signal {signum} reçu, arrêt de l'application...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def _setup_joystick_robot_connection(self):
        """Connecte la manette au robot via callbacks"""
        # Callback de mouvement : manette -> robot
        def joystick_movement_callback(x: float, y: float) -> None:
            """Convertit les mouvements joystick en commandes robot"""
            if abs(y) > 0.1:
                if y > 0:
                    robot_service.execute_command("forward", abs(y))
                else:
                    robot_service.execute_command("backward", abs(y))
            elif abs(x) > 0.1:
                if x > 0:
                    robot_service.execute_command("right", abs(x))
                else:
                    robot_service.execute_command("left", abs(x))
            else:
                robot_service.execute_command("stop")
        
        joystick_service.set_movement_callback(joystick_movement_callback)
        
        # Callback bouton d'arrêt d'urgence
        def emergency_stop_callback(pressed: bool) -> None:
            """Arrêt d'urgence quand bouton pressé"""
            if pressed:
                robot_service.emergency_stop()
        
        joystick_service.set_button_callback(
            config.joystick.button_stop,
            emergency_stop_callback
        )
        
        self.logger.info("Connexion manette-robot configurée")
    
    async def start(self):
        """Démarre tous les services de l'application"""
        if self.is_running:
            self.logger.warning("Application déjà en cours")
            return
        
        self.logger.info("Démarrage de l'application robot...")
        
        try:
            # 1. Démarre la capture vidéo
            if not camera_service.start_capture():
                self.logger.warning("Impossible de démarrer la caméra")
            
            # 2. Démarre la surveillance de la manette
            if not joystick_service.start_monitoring():
                self.logger.warning("Impossible de démarrer la manette")
            
            # 3. Démarre le serveur vidéo
            if not video_server.start():
                self.logger.error("Impossible de démarrer le serveur vidéo")
                return False
            
            # 4. Démarre le serveur de contrôle
            if not await control_server.start():
                self.logger.error("Impossible de démarrer le serveur de contrôle")
                return False
            
            # 5. Démarre le serveur WebSocket
            if not await websocket_server.start():
                self.logger.error("Impossible de démarrer le serveur WebSocket")
                return False
            
            # 6. Démarre le serveur MCP
            if not await mcp_server.start():
                self.logger.warning("Impossible de démarrer le serveur MCP")
            
            self.is_running = True
            
            # Affiche les informations de connexion
            self._print_startup_info()
            
            self.logger.info("🚀 Application démarrée avec succès!")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage: {e}")
            await self.stop()
            return False
    
    def _print_startup_info(self):
        """Affiche les informations de démarrage"""
        print("\n" + "="*60)
        print("🤖 ROBOT APPLICATION DÉMARRÉE")
        print("="*60)
        print(f"🎥 Flux vidéo      : http://{config.web.host}:{config.web.video_port}/video_feed")
        print(f"🎮 API contrôle    : http://{config.web.host}:{config.web.port}")
        print(f"⚡ WebSocket       : ws://{config.web.host}:{config.web.websocket_port}")
        print(f"🔧 Serveur MCP     : ws://{config.mcp.host}:{config.mcp.port}")
        print(f"📊 État robot      : http://{config.web.host}:{config.web.port}/api/status")
        print(f"🏥 Santé services  : http://{config.web.host}:{config.web.port}/api/health")
        print("="*60)
        
        # État des services
        print("📋 ÉTAT DES SERVICES:")
        robot_status = "✅" if robot_service.is_available() else "❌"
        camera_status = "✅" if camera_service.is_available() else "❌"
        joystick_status = "✅" if joystick_service.is_available() else "❌"
        websocket_status = "✅" if websocket_server.is_running else "❌"
        
        print(f"   • Robot         : {robot_status}")
        print(f"   • Caméra        : {camera_status}")
        print(f"   • Manette       : {joystick_status}")
        print(f"   • WebSocket     : {websocket_status}")
        print("="*60)
        
        if config.debug:
            print("🐛 Mode développement activé")
        print("📝 Logs sauvegardés dans: robot_app.log")
        print("🛑 Ctrl+C pour arrêter l'application")
        print()
    
    async def stop(self):
        """Arrête tous les services de l'application"""
        if not self.is_running:
            return
        
        self.logger.info("Arrêt de l'application...")
        
        try:
            # Arrête tous les services en parallèle
            await asyncio.gather(
                # Services asynchrones
                websocket_server.stop(),
                mcp_server.stop(),
                
                # Services synchrones (dans des tâches)
                asyncio.create_task(asyncio.to_thread(self._stop_sync_services)),
                
                return_exceptions=True
            )
            
            self.is_running = False
            self.logger.info("✅ Application arrêtée proprement")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'arrêt: {e}")
    
    def _stop_sync_services(self):
        """Arrête les services synchrones"""
        # Arrête les services de base
        joystick_service.cleanup()
        camera_service.cleanup()
        robot_service.cleanup()
        
        # Arrête les serveurs web
        video_server.stop()
        control_server.stop()
    
    async def run_forever(self):
        """Lance l'application et attend indéfiniment"""
        if not await self.start():
            return
        
        try:
            # Boucle principale simple
            while self.is_running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Interruption clavier détectée")
        finally:
            await self.stop()
    
    def get_status(self) -> dict:
        """Retourne l'état complet de l'application"""
        return {
            "application": {
                "is_running": self.is_running,
                "debug_mode": config.debug
            },
            "services": {
                "robot": robot_service.get_state(),
                "camera": camera_service.get_stats(),
                "joystick": joystick_service.get_state()
            },
            "servers": {
                "websocket_clients": websocket_server.get_client_count(),
                "mcp_connected": mcp_server.is_client_connected()
            }
        }


# Point d'entrée principal
async def main():
    """Point d'entrée principal de l'application"""
    # Configure l'environnement
    if len(sys.argv) > 1:
        env = sys.argv[1].lower()
        if env == "dev":
            configure_for_development()
        elif env == "prod":
            configure_for_production()
    else:
        # Par défaut en mode développement
        configure_for_development()
    
    # Lance l'application
    app = Application()
    await app.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Au revoir!")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
        sys.exit(1)
