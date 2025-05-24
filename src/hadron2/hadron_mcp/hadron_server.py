"""
Serveur MCP (Model Context Protocol) pour le robot Hadron2
Utilise FastMCP pour une intégration simplifiée et efficace
"""

import asyncio
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

# Import des services du robot
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from core.camera_service import CameraService
    from core.joystick_service import JoystickService
    from core.robot_service import RobotService
except ImportError:
    # Fallback pour les tests sans matériel
    print("Services hardware non disponibles - mode simulation")
    RobotService = None
    CameraService = None
    JoystickService = None

# Création de l'instance FastMCP
mcp = FastMCP("hadron")

# Services globaux
robot_service = RobotService() if RobotService else None
camera_service = CameraService() if CameraService else None
joystick_service = JoystickService() if JoystickService else None


@mcp.tool()
def robot_move(
    direction: str, duration: float = 1.0, speed: float = 50.0
) -> dict[str, Any]:
    """
    Contrôle les mouvements du robot.
    
    Args:
        direction: Direction du mouvement (forward, backward, left, right, stop)
        duration: Durée du mouvement en secondes (optionnel)
        speed: Vitesse du mouvement 0-100% (optionnel)
    """
    if not robot_service:
        return {
            "success": False,
            "error": "Service robot non disponible (mode simulation)"
        }
    
    try:
        # Convertit la vitesse de pourcentage à échelle 0-1
        normalized_speed = min(max(speed / 100.0, 0.0), 1.0)
        
        # Exécute la commande de mouvement
        success = robot_service.execute_command(direction, normalized_speed)
        
        if not success:
            return {
                "success": False,
                "error": f"Échec de l'exécution de la commande: {direction}"
            }
        
        # Si une durée est spécifiée et ce n'est pas "stop", programme l'arrêt
        if duration > 0 and direction != "stop":
            async def stop_after_duration():
                await asyncio.sleep(duration)
                robot_service.execute_command("stop")
            
            asyncio.create_task(stop_after_duration())
        
        return {
            "success": True,
            "command": direction,
            "duration": duration,
            "speed": speed,
            "message": f"Mouvement {direction} exécuté avec succès"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur de mouvement: {str(e)}"
        }


@mcp.tool()
def robot_joystick_control(axis_x: float, axis_y: float) -> dict[str, Any]:
    """
    Contrôle le robot avec les axes de la manette.
    
    Args:
        axis_x: Axe horizontal (-1.0 à 1.0)
        axis_y: Axe vertical (-1.0 à 1.0)
    """
    if not robot_service:
        return {
            "success": False,
            "error": "Service robot non disponible (mode simulation)"
        }
    
    try:
        success = robot_service.move_with_joystick(axis_x, axis_y)
        
        if not success:
            return {
                "success": False,
                "error": "Échec du contrôle par manette"
            }
        
        state = robot_service.get_state()
        return {
            "success": True,
            "axis_x": axis_x,
            "axis_y": axis_y,
            "current_command": state["command"],
            "current_speed": state["speed"]
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur contrôle manette: {str(e)}"
        }


@mcp.tool()
def robot_camera(action: str) -> dict[str, Any]:
    """
    Contrôle la caméra du robot.
    
    Args:
        action: Action à effectuer (status, start, stop, capture)
    """
    if not camera_service:
        return {
            "success": False,
            "error": "Service caméra non disponible (mode simulation)"
        }
    
    try:
        if action == "status":
            stats = camera_service.get_stats()
            return {
                "success": True,
                "action": action,
                "status": {
                    "is_running": camera_service.is_running,
                    "fps": stats["fps"],
                    "frames_captured": stats["frames_captured"],
                    "frames_dropped": stats["frames_dropped"]
                }
            }
        elif action == "start":
            success = camera_service.start()
            return {
                "success": success,
                "action": action,
                "message": "Flux vidéo démarré" if success else "Erreur de démarrage"
            }
        elif action == "stop":
            camera_service.stop()
            return {
                "success": True,
                "action": action,
                "message": "Flux vidéo arrêté"
            }
        elif action == "capture":
            frame = camera_service.get_latest_frame()
            if frame is not None:
                return {
                    "success": True,
                    "action": action,
                    "message": "Image capturée",
                    "frame_shape": frame.shape
                }
            else:
                return {
                    "success": False,
                    "action": action,
                    "error": "Aucune image disponible"
                }
        else:
            return {
                "success": False,
                "error": f"Action inconnue: {action}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur caméra: {str(e)}"
        }


@mcp.tool()
def robot_status() -> dict[str, Any]:
    """
    Obtient le statut général du robot.
    """
    status = {
        "robot_name": "Hadron2",
        "architecture": "FastAPI + FastMCP",
        "services": {
            "robot": robot_service is not None and robot_service.is_available(),
            "camera": camera_service is not None,
            "joystick": joystick_service is not None and joystick_service.is_available()
        },
        "mcp_server": "active"
    }
    
    # Ajoute l'état du robot si disponible
    if robot_service:
        robot_state = robot_service.get_state()
        status["robot_state"] = robot_state
    
    # Ajoute les stats de la caméra si disponible
    if camera_service:
        camera_stats = camera_service.get_stats()
        status["camera_stats"] = camera_stats
    
    return {
        "success": True,
        "status": status
    }


@mcp.tool()
def emergency_stop() -> dict[str, Any]:
    """
    Arrêt d'urgence du robot.
    """
    try:
        if robot_service:
            success = robot_service.emergency_stop()
            if not success:
                return {
                    "success": False,
                    "error": "Échec de l'arrêt d'urgence"
                }
        
        return {
            "success": True,
            "message": "Arrêt d'urgence exécuté"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur arrêt d'urgence: {str(e)}"
        }


if __name__ == "__main__":
    # Démarrage du serveur MCP en mode stdio
    mcp.run()