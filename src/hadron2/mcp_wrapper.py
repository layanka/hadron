"""
Wrapper pour FastMCP pour l'intégrer avec l'architecture existante de Hadron2
"""

import logging
import subprocess


class MCPServerWrapper:
    """Wrapper pour FastMCP qui respecte l'interface attendue par l'application"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.process: subprocess.Popen | None = None
        self.is_running = False
        
    async def start(self) -> bool:
        """Démarre le serveur MCP en arrière-plan"""
        try:
            # Le serveur FastMCP est prêt à l'import
            # Il ne nécessite pas de démarrage séparé pour notre usage
            self.is_running = True
            self.logger.info("Serveur MCP FastMCP prêt")
            return True
        except Exception as e:
            self.logger.error(f"Erreur démarrage serveur MCP: {e}")
            return False
    
    async def stop(self):
        """Arrête le serveur MCP"""
        try:
            if self.process:
                self.process.terminate()
                self.process.wait()
                self.process = None
            self.is_running = False
            self.logger.info("Serveur MCP arrêté")
        except Exception as e:
            self.logger.error(f"Erreur arrêt serveur MCP: {e}")
    
    def is_client_connected(self) -> bool:
        """Vérifie si un client MCP est connecté"""
        # Pour FastMCP en mode intégré, on considère qu'il est toujours "connecté"
        return self.is_running
    
    def get_tools(self) -> list:
        """Retourne la liste des outils disponibles"""
        # FastMCP gère les outils via des décorateurs
        return [
            "robot_move",
            "robot_sensors", 
            "robot_camera",
            "robot_status",
            "emergency_stop"
        ]
    
    def execute_tool(self, tool_name: str, **kwargs):
        """Exécute un outil MCP directement"""
        # Import dynamique des fonctions outils pour éviter les imports circulaires
        try:
            from hadron_mcp import hadron_server as mcp_module
            if hasattr(mcp_module, tool_name):
                tool_func = getattr(mcp_module, tool_name)
                return tool_func(**kwargs)
            else:
                raise ValueError(f"Outil inconnu: {tool_name}")
        except ImportError as e:
            self.logger.error(f"Erreur import serveur MCP: {e}")
            return {"success": False, "error": "Serveur MCP non disponible"}


# Instance globale
mcp_server = MCPServerWrapper()
