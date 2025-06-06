"""
Service de gestion de la caméra.
Optimisé pour une latence minimale avec buffer réduit.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable, Generator
import io

import cv2
import libcamera
from libcamera import controls
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder, MJPEGEncoder
from picamera2.outputs import FileOutput

from config import config


class StreamingOutput(io.BufferedIOBase):
    """Sortie de streaming compatible avec picamera2"""
    
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()
    
    def write(self, buf):
        # Cette méthode est appelée par l'encoder
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)

    def flush(self):
        pass


class CameraService:
    """Service de capture vidéo optimisé pour la latence minimale"""
    
    def __init__(self):
        self.camera: Picamera2 | None = None
        self.is_running = False
        self.output = StreamingOutput()
        self.frame_queue = queue.Queue(maxsize=1)  # Buffer minimal
        self.capture_thread: threading.Thread | None = None
        self.logger = logging.getLogger(__name__)
        self.encoder = None
        
        # Statistiques
        self.frames_captured = 0
        self.frames_dropped = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
        
        # Callbacks
        self._frame_callbacks = []
        
        self._initialize_camera()
    
    def _initialize_camera(self):
        """Initialise la caméra avec la configuration optimale"""
        try:
            if config.camera.device_index < 0:
                self.logger.info("Mode test: caméra désactivée")
                return
            
            self.camera = Picamera2()
            
            # Configuration de la caméra
            video_config = self.camera.create_video_configuration(
                main={
                    "size": (config.camera.width, config.camera.height),
                    "format": "RGB888"
                },
                buffer_count=config.camera.buffer_size,
                controls={
                    "FrameRate": config.camera.fps,
                    "FrameDurationLimits": (int(1000000/config.camera.fps), int(1000000/config.camera.fps))
                }
            )
            
            # Application de la transformation (flip)
            video_config["transform"] = libcamera.Transform(
                hflip=config.camera.hflip, 
                vflip=config.camera.vflip
            )
            
            self.camera.configure(video_config)
            
            # Créer l'encoder JPEG
            self.encoder = JpegEncoder(q=config.camera.quality)
                
            self.logger.info(f"Caméra initialisée: {config.camera.width}x{config.camera.height} @ {config.camera.fps}fps")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la caméra: {e}")
            self.camera = None
    
    def add_frame_callback(self, callback: Callable[[bytes], None]):
        """Ajoute un callback appelé pour chaque nouvelle frame"""
        self._frame_callbacks.append(callback)
    
    def _notify_frame_callbacks(self, frame_data: bytes):
        """Notifie tous les callbacks de frame"""
        for callback in self._frame_callbacks:
            try:
                callback(frame_data)
            except Exception as e:
                self.logger.error(f"Erreur dans le callback de frame: {e}")
    
    def _capture_frames(self):
        """Thread de capture des frames en continu"""
        frame_count = 0
        fps_start_time = time.time()
        
        try:
            # Démarrer l'enregistrement avec l'encoder et l'output
            self.camera.start_recording(self.encoder, FileOutput(self.output))
            self.logger.info("Démarrage de la capture vidéo")
            
            while self.is_running and self.camera:
                try:
                    # Attendre une nouvelle frame
                    with self.output.condition:
                        if self.output.condition.wait(timeout=1.0):
                            if self.output.frame is not None:
                                frame_bytes = self.output.frame
                                
                                # Met à jour la queue (supprime l'ancienne frame si pleine)
                                try:
                                    self.frame_queue.put_nowait(frame_bytes)
                                    self.frames_captured += 1
                                except queue.Full:
                                    # Supprime l'ancienne frame et ajoute la nouvelle
                                    try:
                                        self.frame_queue.get_nowait()
                                        self.frames_dropped += 1
                                    except queue.Empty:
                                        pass
                                    
                                    try:
                                        self.frame_queue.put_nowait(frame_bytes)
                                        self.frames_captured += 1
                                    except queue.Full:
                                        pass
                                
                                # Notifie les callbacks
                                self._notify_frame_callbacks(frame_bytes)
                                
                                # Calcule le FPS
                                frame_count += 1
                                if frame_count % 30 == 0:  # Calcule le FPS toutes les 30 frames
                                    current_time = time.time()
                                    elapsed = current_time - fps_start_time
                                    if elapsed > 0:
                                        self.current_fps = 30 / elapsed
                                    fps_start_time = current_time
                        else:
                            # Timeout - pas de nouvelle frame
                            time.sleep(0.01)
                            
                except Exception as e:
                    self.logger.error(f"Erreur dans la capture de frame: {e}")
                    time.sleep(0.01)
                    
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage de l'enregistrement: {e}")
        finally:
            # Arrêter l'enregistrement
            if self.camera:
                try:
                    self.camera.stop_recording()
                except:
                    pass
    
    def start_capture(self) -> bool:
        """Démarre la capture vidéo"""
        if not self.camera:
            self.logger.error("Caméra non initialisée")
            return False
        
        if self.is_running:
            self.logger.warning("Capture déjà en cours")
            return True
        
        self.is_running = True
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()
        
        self.logger.info("Capture vidéo démarrée")
        return True
    
    def stop_capture(self):
        """Arrête la capture vidéo"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
        
        # Vide la queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        
        self.logger.info("Capture vidéo arrêtée")
    
    def get_latest_frame(self) -> bytes | None:
        """Récupère la dernière frame disponible"""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def frame_generator(self) -> Generator[bytes, None, None]:
        """Générateur de frames pour le streaming"""
        while self.is_running:
            frame_data = self.get_latest_frame()
            if frame_data:
                yield frame_data
            else:
                time.sleep(0.001)  # Pause courte si pas de frame
    
    def get_stats(self) -> dict:
        """Retourne les statistiques de capture"""
        return {
            "is_running": self.is_running,
            "current_fps": self.current_fps,
            "frames_captured": self.frames_captured,
            "frames_dropped": self.frames_dropped,
            "drop_rate": self.frames_dropped / max(self.frames_captured, 1) * 100,
            "is_available": self.camera is not None
        }
    
    def is_available(self) -> bool:
        """Vérifie si la caméra est disponible"""
        return self.camera is not None
    
    def cleanup(self):
        """Nettoie les ressources de la caméra"""
        self.stop_capture()
        
        if self.camera:
            try:
                self.camera.close()
                self.logger.info("Caméra fermée")
            except:
                pass
            self.camera = None
        
        self.logger.info("Caméra nettoyée")


# Instance globale du service caméra
camera_service = CameraService()
