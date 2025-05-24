"""
Service de gestion de la manette de jeu.
Utilise le système de callbacks pour un contrôle réactif du robot.
"""

import logging
import threading
from collections.abc import Callable

from config import config
from joystickController import EventType, JoystickConfig, JoystickReader


class JoystickService:
    """Service de gestion de la manette avec callbacks vers le robot"""
    
    def __init__(self):
        self.joystick: JoystickReader | None = None
        self.is_running = False
        self.thread: threading.Thread | None = None
        self.logger = logging.getLogger(__name__)
        
        # Callbacks
        self._movement_callback: Callable[[float, float], None] | None = None
        self._button_callbacks = {}
        self._state_callbacks = []
        
        # État actuel
        self.current_axes = {"x": 0.0, "y": 0.0}
        self.current_buttons = {}
        
        self._initialize_joystick()
    
    def _initialize_joystick(self):
        """Initialise la manette avec la configuration"""
        try:
            # Configuration de la manette
            joystick_config = JoystickConfig(
                device_path=config.joystick.device_path,
                deadzone=config.joystick.deadzone
            )
            
            self.joystick = JoystickReader(joystick_config)
            
            # Configure les callbacks
            self._setup_callbacks()
            
            self.logger.info(f"Manette initialisée: {config.joystick.device_path}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la manette: {e}")
            self.joystick = None
    
    def _setup_callbacks(self):
        """Configure les callbacks de la manette"""
        if not self.joystick:
            return
        
        # Callback pour les axes (mouvement)
        self.joystick.add_callback(EventType.AXIS, self._on_axis_event)
        
        # Callback pour les boutons
        self.joystick.add_callback(EventType.BUTTON, self._on_button_event)
    
    def _on_axis_event(self, event):
        """Gestionnaire des événements d'axe"""
        try:
            axis = event.number
            value = event.normalized_value
            
            # Met à jour l'état des axes
            if axis == config.joystick.axis_x:
                self.current_axes["x"] = value
            elif axis == config.joystick.axis_y:
                self.current_axes["y"] = value
            
            # Appelle le callback de mouvement si configuré
            if (self._movement_callback and 
                axis in [config.joystick.axis_x, config.joystick.axis_y]):
                self._movement_callback(
                    self.current_axes["x"],
                    self.current_axes["y"]
                )
            
            # Notifie les callbacks d'état
            self._notify_state_change()
            
        except Exception as e:
            self.logger.error(f"Erreur dans le gestionnaire d'axe: {e}")
    
    def _on_button_event(self, event):
        """Gestionnaire des événements de bouton"""
        try:
            button = event.number
            pressed = bool(event.value)  # 1 = pressé, 0 = relâché
            
            # Met à jour l'état du bouton
            self.current_buttons[button] = pressed
            
            # Appelle le callback spécifique au bouton
            if button in self._button_callbacks:
                self._button_callbacks[button](pressed)
            
            # Bouton d'arrêt d'urgence
            if button == config.joystick.button_stop and pressed:
                self.logger.info("Bouton d'arrêt d'urgence activé")
                if self._movement_callback:
                    self._movement_callback(0.0, 0.0)  # Arrêt
            
            # Notifie les callbacks d'état
            self._notify_state_change()
            
        except Exception as e:
            self.logger.error(f"Erreur dans le gestionnaire de bouton: {e}")
    
    def set_movement_callback(self, callback: Callable[[float, float], None]):
        """Configure le callback de mouvement (x, y axes)"""
        self._movement_callback = callback
        self.logger.info("Callback de mouvement configuré")
    
    def set_button_callback(self, button: int, callback: Callable[[bool], None]):
        """Configure un callback pour un bouton spécifique"""
        self._button_callbacks[button] = callback
        self.logger.info(f"Callback configuré pour le bouton {button}")
    
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
                msg = f"Erreur dans le callback d'état: {e}"
                self.logger.error(msg)
    
    def get_state(self) -> dict:
        """Retourne l'état actuel de la manette"""
        device_info = self.joystick.get_device_info() if self.joystick else None
        is_connected = (device_info is not None and 
                       device_info.is_available if device_info else False)
        
        return {
            "is_connected": is_connected,
            "is_running": self.is_running,
            "axes": self.current_axes.copy(),
            "buttons": self.current_buttons.copy(),
            "stats": self.joystick.get_stats() if self.joystick else {}
        }
    
    def start_monitoring(self) -> bool:
        """Démarre la surveillance de la manette"""
        if not self.joystick:
            self.logger.error("Manette non initialisée")
            return False
        
        if self.is_running:
            self.logger.warning("Surveillance déjà en cours")
            return True
        
        try:
            self.is_running = True
            self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.thread.start()
            
            self.logger.info("Surveillance de la manette démarrée")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage de la surveillance: {e}")
            self.is_running = False
            return False
    
    def _monitor_loop(self):
        """Boucle de surveillance de la manette"""
        if not self.joystick:
            return
        
        try:
            # Utilise la nouvelle API avec read_events() dans un générateur
            for _ in self.joystick.read_events():
                if not self.is_running:
                    break
                    
                # L'événement déclenche automatiquement les callbacks configurés
                # via add_callback() - pas besoin de traitement supplémentaire ici
                    
        except Exception as e:
            self.logger.error(f"Erreur dans la boucle de surveillance: {e}")
        finally:
            self.is_running = False
    
    def stop_monitoring(self):
        """Arrête la surveillance de la manette"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.joystick:
            self.joystick.stop()  # Nouvelle méthode stop()
        
        if self.thread:
            self.thread.join(timeout=1.0)
        
        self.logger.info("Surveillance de la manette arrêtée")
    
    def is_available(self) -> bool:
        """Vérifie si la manette est disponible"""
        if not self.joystick:
            return False
        
        device_info = self.joystick.get_device_info()
        return device_info is not None and device_info.is_available
    
    def get_device_info(self) -> dict:
        """Retourne les informations sur le périphérique"""
        if self.joystick:
            device_info = self.joystick.get_device_info()
            return device_info.__dict__ if device_info else {}
        return {}
    
    def cleanup(self):
        """Nettoie les ressources de la manette"""
        self.stop_monitoring()
        self.logger.info("Service manette nettoyé")


# Instance globale du service manette
joystick_service = JoystickService()
