"""
Sistema avanzado de rate limiting por usuario y tipo de operación
Implementa límites configurables para downloads, comandos y búsquedas
"""

import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum
import logging

class RateLimitType(Enum):
    """Tipos de rate limiting disponibles"""
    DOWNLOADS = "downloads"
    COMMANDS = "commands" 
    SEARCHES = "searches"

class RateLimitResult:
    """Resultado de verificación de rate limit"""
    def __init__(self, allowed: bool, remaining_time: Optional[timedelta] = None, 
                 requests_left: int = 0):
        self.allowed = allowed
        self.remaining_time = remaining_time
        self.requests_left = requests_left

class RateLimiter:
    """
    Rate limiter por usuario con ventana deslizante
    Cada instancia maneja un tipo específico de operación
    """
    
    def __init__(self, max_requests: int, time_window: timedelta, 
                 limit_type: RateLimitType):
        self.max_requests = max_requests
        self.time_window = time_window
        self.limit_type = limit_type
        
        # Requests por usuario: {user_id: deque[timestamp]}
        self.user_requests: Dict[int, deque] = defaultdict(deque)
        # Locks por usuario para thread safety
        self.user_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()
        
        logging.info(f"RateLimiter {limit_type.value}: {max_requests} requests per {time_window}")
    
    async def check_limit(self, user_id: int) -> RateLimitResult:
        """
        Verifica si el usuario puede hacer una solicitud
        Si está permitido, registra la nueva solicitud automáticamente
        """
        async with self.user_locks[user_id]:
            now = datetime.now()
            user_queue = self.user_requests[user_id]
            
            # Limpiar solicitudes antiguas fuera de la ventana
            while user_queue and user_queue[0] < now - self.time_window:
                user_queue.popleft()
            
            requests_left = max(0, self.max_requests - len(user_queue))
            
            if len(user_queue) >= self.max_requests:
                # Usuario ha alcanzado el límite
                oldest_request = user_queue[0]
                remaining_time = oldest_request + self.time_window - now
                return RateLimitResult(False, remaining_time, 0)
            
            # Permitir solicitud y registrarla
            user_queue.append(now)
            return RateLimitResult(True, None, requests_left - 1)
    
    async def get_status(self, user_id: int) -> Tuple[int, int]:
        """
        Obtiene el estado actual del usuario (requests_used, requests_remaining)
        """
        async with self.user_locks[user_id]:
            now = datetime.now()
            user_queue = self.user_requests[user_id]
            
            # Limpiar solicitudes antiguas
            while user_queue and user_queue[0] < now - self.time_window:
                user_queue.popleft()
            
            used = len(user_queue)
            remaining = max(0, self.max_requests - used)
            return used, remaining
    
    async def reset_user(self, user_id: int):
        """
        Resetea los límites para un usuario específico (admin only)
        """
        async with self.user_locks[user_id]:
            self.user_requests[user_id].clear()
            logging.info(f"Rate limit reseteado para usuario {user_id} ({self.limit_type.value})")
    
    async def cleanup_old_entries(self):
        """
        Limpia entradas antiguas de todos los usuarios para liberar memoria
        Ejecutado periódicamente por el bot
        """
        async with self._global_lock:
            now = datetime.now()
            cutoff = now - self.time_window
            users_cleaned = 0
            
            for user_id in list(self.user_requests.keys()):
                async with self.user_locks[user_id]:
                    user_queue = self.user_requests[user_id]
                    
                    # Limpiar entradas antiguas
                    while user_queue and user_queue[0] < cutoff:
                        user_queue.popleft()
                    
                    # Si la cola está vacía, eliminar usuario completamente
                    if not user_queue:
                        del self.user_requests[user_id]
                        del self.user_locks[user_id]
                        users_cleaned += 1
            
            if users_cleaned > 0:
                logging.debug(f"Rate limiter {self.limit_type.value}: limpiados {users_cleaned} usuarios inactivos")
    
    def get_stats(self) -> Dict[str, int]:
        """Retorna estadísticas del rate limiter"""
        return {
            "active_users": len(self.user_requests),
            "max_requests": self.max_requests,
            "time_window_minutes": int(self.time_window.total_seconds() / 60)
        }

class RateLimitManager:
    """
    Gestor centralizado de múltiples rate limiters
    Maneja downloads, comandos y búsquedas por separado
    """
    
    def __init__(self, download_config: tuple, command_config: tuple, search_config: tuple):
        """
        Inicializa con configuraciones para cada tipo de rate limit
        Cada config es (max_requests, time_window)
        """
        self.limiters = {
            RateLimitType.DOWNLOADS: RateLimiter(*download_config, RateLimitType.DOWNLOADS),
            RateLimitType.COMMANDS: RateLimiter(*command_config, RateLimitType.COMMANDS), 
            RateLimitType.SEARCHES: RateLimiter(*search_config, RateLimitType.SEARCHES)
        }
        
        logging.info("RateLimitManager inicializado con 3 tipos de límites")
    
    async def check_limit(self, user_id: int, limit_type: RateLimitType) -> RateLimitResult:
        """
        Verifica límite para un tipo específico de operación
        """
        return await self.limiters[limit_type].check_limit(user_id)
    
    async def get_all_status(self, user_id: int) -> Dict[str, Tuple[int, int]]:
        """
        Obtiene el estado de todos los limiters para un usuario
        Retorna dict con {tipo: (usado, restante)}
        """
        status = {}
        for limit_type, limiter in self.limiters.items():
            used, remaining = await limiter.get_status(user_id)
            status[limit_type.value] = (used, remaining)
        return status
    
    async def reset_user(self, user_id: int):
        """
        Resetea todos los límites para un usuario (admin only)
        """
        for limiter in self.limiters.values():
            await limiter.reset_user(user_id)
        
        logging.info(f"Todos los rate limits reseteados para usuario {user_id}")
    
    async def cleanup_all(self):
        """
        Ejecuta limpieza en todos los limiters
        """
        for limiter in self.limiters.values():
            await limiter.cleanup_old_entries()
    
    def get_all_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Retorna estadísticas de todos los rate limiters
        """
        return {
            limit_type.value: limiter.get_stats()
            for limit_type, limiter in self.limiters.items()
        }
    
    def format_status_message(self, user_id: int, status: Dict[str, Tuple[int, int]]) -> str:
        """
        Formatea el estado de rate limits para mostrar al usuario
        """
        lines = ["📊 **Estado de Rate Limits**\n"]
        
        type_names = {
            "downloads": "📥 Descargas",
            "commands": "⌨️ Comandos", 
            "searches": "🔍 Búsquedas"
        }
        
        for limit_type, (used, remaining) in status.items():
            name = type_names.get(limit_type, limit_type.title())
            total = used + remaining
            lines.append(f"{name}: {used}/{total} (restantes: {remaining})")
        
        return "\n".join(lines)
    
    def format_limit_exceeded_message(self, limit_type: RateLimitType, 
                                    remaining_time: timedelta) -> str:
        """
        Formatea mensaje cuando se excede un rate limit
        """
        minutes = int(remaining_time.total_seconds() / 60)
        seconds = int(remaining_time.total_seconds() % 60)
        
        type_emojis = {
            RateLimitType.DOWNLOADS: "📥",
            RateLimitType.COMMANDS: "⌨️",
            RateLimitType.SEARCHES: "🔍"
        }
        
        emoji = type_emojis.get(limit_type, "⏱️")
        type_name = limit_type.value
        
        if minutes > 0:
            time_str = f"{minutes} minutos"
            if seconds > 0:
                time_str += f" y {seconds} segundos"
        else:
            time_str = f"{seconds} segundos"
        
        return (f"{emoji} **Límite de {type_name} alcanzado**\n\n"
                f"Intenta nuevamente en {time_str}.")

# Función helper para crear RateLimitManager desde configuración
def create_rate_limit_manager_from_config(config) -> RateLimitManager:
    """
    Crea RateLimitManager usando la configuración del bot
    """
    download_config = (config.RATE_LIMIT_DOWNLOADS_PER_HOUR, timedelta(hours=1))
    command_config = (config.RATE_LIMIT_COMMANDS_PER_MINUTE, timedelta(minutes=1))
    search_config = (config.RATE_LIMIT_SEARCHES_PER_HOUR, timedelta(hours=1))
    
    return RateLimitManager(download_config, command_config, search_config)