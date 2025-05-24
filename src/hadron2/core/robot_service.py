"""
Service de gestion du robot.
Encapsule toute la logique de contrôle des moteurs et mouvements.
"""

import logging
import time
from collections.abc import Callable
from threading import Lock

from carController import RobotCar
from config import config


class RobotService:
    """Service de contrôle du robot avec gestion d'état et callbacks"""
    
    def __init__(self):
        self.robot: RobotCar | None = None
        self.current_command = "stop"
        self.current_speed = 0.0
        self._lock = Lock()
        self._state_callbacks = []
        self.logger = logging.getLogger(__name__)
        
        # État du robot
        self.is_moving = False
        self.last_command_time = time.time()
        
        self._initialize_robot()
    
    def _initialize_robot(self):
        """Initialise le robot avec la configuration"""
        try:
            # Créer la configuration moteur selon l'API RobotCar
            from carController import MotorSetup
            motor_config = MotorSetup(
                left_motor_port=config.robot.left_motor_port,
                right_motor_port=config.robot.right_motor_port,
                left_motor_inverted=config.robot.left_motor_inverted,
                right_motor_inverted=config.robot.right_motor_inverted
            )
            
            self.robot = RobotCar(
                left_trim=config.robot.left_trim,
                right_trim=config.robot.right_trim,
                stop_at_exit=True,
                motor_config=motor_config
            )
            self.logger.info("Robot initialisé avec succès")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du robot: {e}")
            self.robot = None
    
    def add_state_callback(self, callback: Callable[[dict], None]):
        """Ajoute un callback appelé lors des changements d'état"""
        self._state_callbacks.append(callback)
    
    def _notify_state_change(self):
        """Notifie tous les callbacks des changements d'état"""
        state = self.get_state()
        for callback in self._state_callbacks:
            try:
                callback(state)
            except Exception as e:
                self.logger.error(f"Erreur dans le callback d'état: {e}")
    
    def get_state(self) -> dict:
        """Retourne l'état actuel du robot"""
        return {
            "command": self.current_command,
            "speed": self.current_speed,
            "is_moving": self.is_moving,
            "is_connected": self.robot is not None,
            "last_command_time": self.last_command_time
        }
    
    def execute_command(self, command: str, speed: float = None) -> bool:
        """
        Exécute une commande de mouvement
        
        Args:
            command: Commande (forward, backward, left, right, stop)
            speed: Vitesse optionnelle (0.0 à 1.0)
        
        Returns:
            True si la commande a été exécutée avec succès
        """
        if not self.robot:
            self.logger.warning("Robot non initialisé")
            return False
        
        with self._lock:
            try:
                # Utilise la vitesse configurée par défaut si non spécifiée
                if speed is None:
                    if command in ["left", "right"]:
                        speed = config.robot.turn_speed
                    else:
                        speed = config.robot.max_speed
                
                # Exécute la commande
                if command == config.robot.cmd_forward:
                    self.robot.forward(speed)
                elif command == config.robot.cmd_backward:
                    self.robot.backward(speed)
                elif command == config.robot.cmd_left:
                    self.robot.turn_left(speed)
                elif command == config.robot.cmd_right:
                    self.robot.turn_right(speed)
                elif command == config.robot.cmd_stop:
                    self.robot.stop()
                    speed = 0.0
                else:
                    self.logger.warning(f"Commande inconnue: {command}")
                    return False
                
                # Met à jour l'état
                old_command = self.current_command
                self.current_command = command
                self.current_speed = speed
                self.is_moving = command != "stop"
                self.last_command_time = time.time()
                
                # Log uniquement si la commande change
                if old_command != command:
                    self.logger.info(f"Commande exécutée: {command} (vitesse: {speed:.2f})")
                
                # Notifie les callbacks
                self._notify_state_change()
                
                return True
                
            except Exception as e:
                self.logger.error(f"Erreur lors de l'exécution de la commande {command}: {e}")
                return False
    
    def move_with_joystick(self, axis_x: float, axis_y: float) -> bool:
        """
        Contrôle le robot avec les axes de la manette
        
        Args:
            axis_x: Axe horizontal (-1.0 à 1.0)
            axis_y: Axe vertical (-1.0 à 1.0)
        
        Returns:
            True si le mouvement a été exécuté
        """
        # Applique la deadzone
        if abs(axis_x) < config.joystick.deadzone and abs(axis_y) < config.joystick.deadzone:
            return self.execute_command("stop")
        
        # Détermine la commande basée sur les axes
        if abs(axis_y) > abs(axis_x):
            # Mouvement avant/arrière prioritaire
            if axis_y > config.joystick.deadzone:
                command = "backward"  # Axe Y inversé
                speed = abs(axis_y)
            elif axis_y < -config.joystick.deadzone:
                command = "forward"
                speed = abs(axis_y)
            else:
                command = "stop"
                speed = 0.0
        else:
            # Mouvement gauche/droite
            if axis_x > config.joystick.deadzone:
                command = "right"
                speed = abs(axis_x) * config.robot.turn_speed
            elif axis_x < -config.joystick.deadzone:
                command = "left"
                speed = abs(axis_x) * config.robot.turn_speed
            else:
                command = "stop"
                speed = 0.0
        
        return self.execute_command(command, speed)
    
    def emergency_stop(self) -> bool:
        """Arrêt d'urgence du robot"""
        self.logger.warning("ARRÊT D'URGENCE ACTIVÉ")
        return self.execute_command("stop")
    
    def is_available(self) -> bool:
        """Vérifie si le robot est disponible"""
        return self.robot is not None
    
    def cleanup(self):
        """Nettoie les ressources du robot"""
        if self.robot:
            self.robot.stop()
            # RobotCar n'a pas de méthode cleanup, on fait juste stop()
            self.logger.info("Robot nettoyé")


# Instance globale du service robot
robot_service = RobotService()
