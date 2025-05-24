"""
Contrôleur joystick avancé pour Raspberry Pi avec support complet des événements,
callbacks, configuration et monitoring.
"""

import glob
import logging
import struct
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# Configuration et constantes
class EventType(Enum):
    """Types d'événements joystick selon la spécification Linux input"""
    INIT = 0x80  # Événement d'initialisation
    BUTTON = 0x01  # Bouton pressé/relâché
    AXIS = 0x02  # Mouvement d'axe analogique


class ButtonState(Enum):
    """États des boutons"""
    RELEASED = 0
    PRESSED = 1


@dataclass
class JoystickEvent:
    """Représente un événement joystick structuré"""
    timestamp: int
    event_type: EventType
    number: int  # Numéro du bouton/axe
    value: int  # Valeur de l'événement
    raw_type: int  # Type d'événement brut pour debugging
    
    @property
    def normalized_value(self) -> float:
        """Retourne la valeur normalisée pour les axes (-1.0 à 1.0)"""
        if self.event_type == EventType.AXIS:
            return self.value / 32767.0
        return float(self.value)


@dataclass
class JoystickConfig:
    """Configuration du lecteur joystick"""
    device_path: str = "/dev/input/js0"
    deadzone: float = 0.1  # Zone morte pour les axes analogiques (0-1)
    axis_scale: float = 1.0  # Facteur d'échelle pour les axes
    auto_detect: bool = True  # Détection automatique du joystick
    timeout: float | None = None  # Timeout de lecture en secondes
    enable_init_events: bool = False  # Traiter les événements d'initialisation


@dataclass
class DeviceInfo:
    """Informations sur le dispositif joystick"""
    path: str
    name: str | None = None
    vendor_id: str | None = None
    product_id: str | None = None
    is_available: bool = False
    
    def __str__(self) -> str:
        return f"Joystick({self.name or 'Inconnu'}) at {self.path}"


# Setup logging
logger = logging.getLogger(__name__)


class JoystickReader:
    """Lecteur d'événements joystick avancé avec support de configuration et callbacks."""

    def __init__(self, config: JoystickConfig | None = None):
        """Initialise le lecteur joystick.
        
        Args:
            config: Configuration du joystick. Si None, utilise la config par défaut.
        """
        self._config = config or JoystickConfig()
        self._event_format = "IhBB"  # (time, value, type, number)
        self._event_size = struct.calcsize(self._event_format)
        self._callbacks: dict[EventType, list[Callable[[JoystickEvent], None]]] = {
            EventType.BUTTON: [],
            EventType.AXIS: [],
            EventType.INIT: []
        }
        self._device_info: DeviceInfo | None = None
        self._is_running = False
        self._event_count = 0
        self._error_count = 0
        self._start_time: float = 0
        
        # Auto-détection du joystick si activée
        if self._config.auto_detect:
            detected_device = self._auto_detect_joystick()
            if detected_device:
                self._config.device_path = detected_device.path
                self._device_info = detected_device
                logger.info(f"Joystick auto-détecté: {detected_device}")
        
        # Validation du dispositif
        self._validate_device()
        
        logger.info(f"JoystickReader initialisé pour {self._config.device_path}")

    def _auto_detect_joystick(self) -> DeviceInfo | None:
        """Détecte automatiquement le premier joystick disponible."""
        try:
            js_devices = glob.glob("/dev/input/js*")
            if not js_devices:
                logger.warning("Aucun dispositif joystick trouvé")
                return None
            
            # Prendre le premier dispositif disponible
            device_path = js_devices[0]
            device_info = DeviceInfo(
                path=device_path,
                is_available=Path(device_path).exists()
            )
            
            # Tenter de lire les informations du dispositif
            try:
                device_info.name = self._get_device_name(device_path)
            except Exception as e:
                logger.debug(f"Impossible de lire le nom du dispositif: {e}")
            
            return device_info
            
        except Exception as e:
            logger.error(f"Erreur lors de l'auto-détection: {e}")
            return None

    def _get_device_name(self, device_path: str) -> str | None:
        """Récupère le nom du dispositif joystick."""
        try:
            # Sur Linux, on peut lire le nom depuis /proc/bus/input/devices
            # Pour simplifier, on retourne juste le nom du fichier
            return Path(device_path).name
        except Exception:
            return None

    def _validate_device(self) -> None:
        """Valide que le dispositif joystick est accessible."""
        device_path = Path(self._config.device_path)
        
        if not device_path.exists():
            raise FileNotFoundError(
                f"Dispositif joystick non trouvé: {self._config.device_path}"
            )
        
        # Test d'accès en lecture
        try:
            with open(self._config.device_path, "rb") as f:
                f.read(0)  # Test de lecture vide
        except PermissionError:
            raise PermissionError(
                f"Permission refusée pour {self._config.device_path}. "
                "Essayez de lancer le script avec sudo ou ajoutez votre "
                "utilisateur au groupe 'input'"
            )

    def add_callback(
        self, 
        event_type: EventType, 
        callback: Callable[[JoystickEvent], None]
    ) -> None:
        """Ajoute un callback pour un type d'événement spécifique.
        
        Args:
            event_type: Type d'événement à écouter
            callback: Fonction à appeler lors de l'événement
        """
        if event_type not in self._callbacks:
            raise ValueError(f"Type d'événement non supporté: {event_type}")
        
        self._callbacks[event_type].append(callback)
        logger.debug(f"Callback ajouté pour {event_type.name}")

    def remove_callback(
        self, 
        event_type: EventType, 
        callback: Callable[[JoystickEvent], None]
    ) -> bool:
        """Supprime un callback spécifique.
        
        Args:
            event_type: Type d'événement
            callback: Fonction à supprimer
            
        Returns:
            True si le callback a été supprimé, False sinon
        """
        try:
            self._callbacks[event_type].remove(callback)
            logger.debug(f"Callback supprimé pour {event_type.name}")
            return True
        except (ValueError, KeyError):
            return False

    def _normalize_axis_value(self, raw_value: int) -> float:
        """Normalise une valeur d'axe brute en valeur flottante [-1.0, 1.0]."""
        # Les valeurs d'axe vont généralement de -32768 à 32767
        normalized = raw_value / 32767.0
        
        # Appliquer la zone morte
        if abs(normalized) < self._config.deadzone:
            normalized = 0.0
        
        # Appliquer le facteur d'échelle
        normalized *= self._config.axis_scale
        
        # S'assurer que la valeur reste dans [-1.0, 1.0]
        return max(-1.0, min(1.0, normalized))

    def _process_event(self, raw_event: dict[str, Any]) -> JoystickEvent | None:
        """Traite un événement brut et le convertit en JoystickEvent."""
        try:
            # Déterminer le type d'événement
            raw_type = raw_event["type"]
            
            if raw_type & 0x80:  # Événement d'initialisation
                if not self._config.enable_init_events:
                    return None
                event_type = EventType.INIT
            elif raw_type == 0x01:  # Bouton
                event_type = EventType.BUTTON
            elif raw_type == 0x02:  # Axe
                event_type = EventType.AXIS
            else:
                logger.debug(f"Type d'événement inconnu: {raw_type}")
                return None
            
            # Créer l'événement structuré
            event = JoystickEvent(
                timestamp=raw_event["time"],
                event_type=event_type,
                number=raw_event["number"],
                value=raw_event["value"],
                raw_type=raw_type
            )
            
            return event
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement de l'événement: {e}")
            self._error_count += 1
            return None

    def _fire_callbacks(self, event: JoystickEvent) -> None:
        """Déclenche les callbacks pour un événement donné."""
        callbacks = self._callbacks.get(event.event_type, [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Erreur dans callback {event.event_type.name}: {e}")

    def read_events(self) -> Generator[JoystickEvent, None, None]:
        """Lit les événements du joystick et les retourne sous forme de JoystickEvent.
        
        Yields:
            JoystickEvent: Événements joystick structurés
        """
        self._is_running = True
        self._event_count = 0
        self._error_count = 0
        self._start_time = time.time()
        
        logger.info(f"Début de lecture des événements sur {self._config.device_path}")
        
        try:
            with open(self._config.device_path, "rb") as device:
                
                while self._is_running:
                    # Vérifier le timeout
                    if (self._config.timeout and 
                        time.time() - self._start_time > self._config.timeout):
                        logger.info("Timeout atteint, arrêt de la lecture")
                        break
                    
                    # Lire l'événement brut
                    try:
                        raw_data = device.read(self._event_size)
                        if not raw_data:
                            logger.debug("Fin des données, arrêt de la lecture")
                            break
                        
                        # Décomposer l'événement
                        timestamp, value, event_type, number = struct.unpack(
                            self._event_format, raw_data
                        )
                        
                        raw_event = {
                            "time": timestamp,
                            "value": value,
                            "type": event_type,
                            "number": number,
                        }
                        
                        # Traiter l'événement
                        event = self._process_event(raw_event)
                        if event:
                            self._event_count += 1
                            
                            # Déclencher les callbacks
                            self._fire_callbacks(event)
                            
                            # Yielder l'événement
                            yield event
                            
                    except struct.error as e:
                        logger.error(f"Erreur de décodage: {e}")
                        self._error_count += 1
                        continue
                    
        except FileNotFoundError:
            error_msg = (
                f"Dispositif {self._config.device_path} non trouvé. "
                "Vérifiez que le contrôleur est connecté."
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        except PermissionError:
            error_msg = (
                "Permission refusée. Essayez de lancer le script avec sudo "
                "ou ajoutez votre utilisateur au groupe 'input'."
            )
            logger.error(error_msg)
            raise PermissionError(error_msg)
            
        except OSError as e:
            error_msg = f"Erreur d'accès à {self._config.device_path}: {e}"
            logger.error(error_msg)
            raise OSError(error_msg)
            
        finally:
            self._is_running = False
            duration = time.time() - self._start_time
            logger.info(
                f"Lecture terminée après {duration:.2f}s. "
                f"Événements traités: {self._event_count}, "
                f"Erreurs: {self._error_count}"
            )

    def stop(self) -> None:
        """Arrête la lecture des événements."""
        self._is_running = False
        logger.info("Arrêt demandé pour la lecture des événements")

    def get_device_info(self) -> DeviceInfo | None:
        """Retourne les informations sur le dispositif joystick."""
        return self._device_info

    def get_stats(self) -> dict[str, Any]:
        """Retourne les statistiques de lecture."""
        duration = time.time() - self._start_time if self._start_time else 0
        return {
            "event_count": self._event_count,
            "error_count": self._error_count,
            "is_running": self._is_running,
            "duration_seconds": duration,
            "events_per_second": self._event_count / duration if duration > 0 else 0,
            "device_path": self._config.device_path,
            "config": {
                "deadzone": self._config.deadzone,
                "axis_scale": self._config.axis_scale,
                "auto_detect": self._config.auto_detect,
                "timeout": self._config.timeout,
                "enable_init_events": self._config.enable_init_events,
            }
        }

    @staticmethod
    def list_available_joysticks() -> list[DeviceInfo]:
        """Liste tous les joysticks disponibles sur le système."""
        devices = []
        
        try:
            js_devices = glob.glob("/dev/input/js*")
            for device_path in js_devices:
                device_info = DeviceInfo(
                    path=device_path,
                    is_available=Path(device_path).exists()
                )
                
                # Tenter de récupérer le nom
                try:
                    device_info.name = Path(device_path).name
                except Exception:
                    pass
                
                devices.append(device_info)
                
        except Exception as e:
            logger.error(f"Erreur lors de la liste des joysticks: {e}")
        
        return devices

    def __enter__(self):
        """Support du context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique à la sortie du context manager."""
        self.stop()


# Classes utilitaires pour le mapping des événements
class JoystickMapper:
    """Mappe les événements joystick vers des actions spécifiques."""
    
    def __init__(self):
        self._button_mappings: dict[int, Callable[[], None]] = {}
        self._axis_mappings: dict[int, Callable[[float], None]] = {}
    
    def map_button(self, button_number: int, action: Callable[[], None]) -> None:
        """Mappe un bouton vers une action."""
        self._button_mappings[button_number] = action
        logger.debug(f"Bouton {button_number} mappé vers {action.__name__}")
    
    def map_axis(self, axis_number: int, action: Callable[[float], None]) -> None:
        """Mappe un axe vers une action (reçoit la valeur normalisée)."""
        self._axis_mappings[axis_number] = action
        logger.debug(f"Axe {axis_number} mappé vers {action.__name__}")
    
    def handle_event(self, event: JoystickEvent) -> bool:
        """Traite un événement selon les mappings configurés.
        
        Returns:
            True si l'événement a été traité, False sinon
        """
        try:
            if event.event_type == EventType.BUTTON:
                if event.number in self._button_mappings and event.value == 1:
                    # Seulement déclencher sur appui (value=1), pas relâchement (value=0)
                    self._button_mappings[event.number]()
                    return True
            
            elif event.event_type == EventType.AXIS:
                if event.number in self._axis_mappings:
                    normalized_value = event.normalized_value
                    self._axis_mappings[event.number](normalized_value)
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement du mapping: {e}")
            return False


# Exemple d'utilisation
def example_usage():
    """Exemple d'utilisation du JoystickReader amélioré."""
    
    # Configuration personnalisée
    config = JoystickConfig(
        deadzone=0.15,
        axis_scale=0.8,
        auto_detect=True,
        timeout=30.0  # 30 secondes de timeout
    )
    
    # Créer le lecteur avec context manager
    with JoystickReader(config) as joystick:
        
        # Ajouter des callbacks
        def on_button_event(event: JoystickEvent):
            if event.value == 1:  # Bouton pressé
                print(f"Bouton {event.number} pressé!")
        
        def on_axis_event(event: JoystickEvent):
            normalized = event.normalized_value
            print(f"Axe {event.number}: {normalized:.2f}")
        
        joystick.add_callback(EventType.BUTTON, on_button_event)
        joystick.add_callback(EventType.AXIS, on_axis_event)
        
        # Créer un mapper pour des actions spécifiques
        mapper = JoystickMapper()
        
        def move_forward():
            print("Action: Avancer!")
        
        def steer(value: float):
            print(f"Action: Tourner à {value:.2f}")
        
        mapper.map_button(0, move_forward)  # Bouton 0 -> avancer
        mapper.map_axis(0, steer)  # Axe 0 -> direction
        
        # Lire les événements
        try:
            for event in joystick.read_events():
                # Le mapper traite les événements selon la configuration
                mapper.handle_event(event)
                
                # Afficher les stats périodiquement
                if joystick.get_stats()["event_count"] % 100 == 0:
                    stats = joystick.get_stats()
                    print(f"Stats: {stats['event_count']} événements, "
                          f"{stats['events_per_second']:.1f} evt/s")
                
        except KeyboardInterrupt:
            print("Arrêt demandé par l'utilisateur")
            
        # Les stats finales sont automatiquement affichées grâce au context manager


if __name__ == "__main__":
    # Lister les joysticks disponibles
    available = JoystickReader.list_available_joysticks()
    print("Joysticks disponibles:")
    for device in available:
        print(f"  - {device}")
    
    if available:
        example_usage()
    else:
        print("Aucun joystick trouvé!")
