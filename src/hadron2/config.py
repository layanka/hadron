"""
Configuration centralisée pour l'application robot.
Contient tous les paramètres configurables pour une maintenance facile.
"""

from dataclasses import dataclass


@dataclass
class CameraConfig:
    """Configuration de la caméra"""
    width: int = 640
    height: int = 480
    fps: int = 30
    buffer_size: int = 1  # Buffer minimal pour réduire la latence
    device_index: int = 0
    quality: int = 85  # Qualité JPEG (0-100)
    vflip: int = 1  # Vertical flip
    hflip: int = 1  # Horizontal flip
    


@dataclass
class RobotConfig:
    """Configuration du robot"""
    # Configuration moteurs (compatible avec RobotCar)
    left_motor_port: int = 2
    right_motor_port: int = 1
    left_motor_inverted: bool = True
    right_motor_inverted: bool = False
    left_trim: float = 0.0
    right_trim: float = 0.0
    
    # Vitesses
    max_speed: float = 1.0
    turn_speed: float = 0.8
    acceleration: float = 0.1
    deceleration: float = 0.2
    
    # Commandes (rétrocompatibilité)
    cmd_forward: str = "forward"
    cmd_backward: str = "backward"
    cmd_left: str = "left"
    cmd_right: str = "right"
    cmd_stop: str = "stop"


@dataclass
class JoystickConfig:
    """Configuration de la manette"""
    device_path: str = "/dev/input/js0"
    deadzone: float = 0.1
    axis_x: int = 0  # Axe horizontal (gauche/droite)
    axis_y: int = 1  # Axe vertical (avant/arrière)
    button_stop: int = 0  # Bouton d'arrêt d'urgence


@dataclass
class WebConfig:
    """Configuration des services web"""
    host: str = "0.0.0.0"
    port: int = 8080
    video_port: int = 8081
    websocket_port: int = 8082
    websocket_frequency: int = 200  # Hz - Haute fréquence pour faible latence
    
    # CORS
    cors_origins: list = None
    
    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = ["*"]


@dataclass
class MCPConfig:
    """Configuration du serveur MCP"""
    host: str = "0.0.0.0"
    port: int = 8083
    websocket_path: str = "/mcp"


@dataclass
class AppConfig:
    """Configuration principale de l'application"""
    camera: CameraConfig = None
    robot: RobotConfig = None
    joystick: JoystickConfig = None
    web: WebConfig = None
    mcp: MCPConfig = None
    
    # Mode de développement
    debug: bool = False
    log_level: str = "INFO"
    
    def __post_init__(self):
        if self.camera is None:
            self.camera = CameraConfig()
        if self.robot is None:
            self.robot = RobotConfig()
        if self.joystick is None:
            self.joystick = JoystickConfig()
        if self.web is None:
            self.web = WebConfig()
        if self.mcp is None:
            self.mcp = MCPConfig()


# Instance globale de configuration
config = AppConfig()

# Configuration pour différents environnements
def configure_for_development():
    """Configuration optimisée pour le développement"""
    config.debug = True
    config.log_level = "DEBUG"
    config.camera.quality = 70  # Qualité réduite pour le dev
    config.web.websocket_frequency = 100  # Fréquence réduite


def configure_for_production():
    """Configuration optimisée pour la production"""
    config.debug = False
    config.log_level = "INFO"
    config.camera.quality = 85
    config.web.websocket_frequency = 200  # Haute fréquence


def configure_for_testing():
    """Configuration pour les tests"""
    config.debug = True
    config.log_level = "DEBUG"
    config.camera.device_index = -1  # Pas de vraie caméra
    config.joystick.device_path = "/dev/null"  # Pas de vraie manette
