import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from typing import Dict, Any, Optional
import time

def validate_telegram_data(init_data: str, token: str, expire_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    """
    Valida los datos de inicialización de Telegram Mini App.
    
    Args:
        init_data: String query string recibido del frontend (WebApp.initData).
        token: Token del bot de Telegram.
        expire_seconds: Tiempo de expiración en segundos (default 24h).
        
    Returns:
        Dict con los datos del usuario si es válido, None si es inválido.
    """
    try:
        parsed_data = dict(parse_qsl(init_data))
    except ValueError:
        return None

    if "hash" not in parsed_data:
        return None

    received_hash = parsed_data.pop("hash")
    
    # Ordenar claves alfabéticamente
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed_data.items())
    )
    
    # Calcular HMAC-SHA256
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != received_hash:
        return None
        
    # Verificar expiración (auth_date)
    auth_date = int(parsed_data.get("auth_date", 0))
    if time.time() - auth_date > expire_seconds:
        return None
        
    # Parsear el objeto 'user' JSON si existe
    user_data = parsed_data
    if "user" in parsed_data:
        try:
            user_data["user"] = json.loads(parsed_data["user"])
        except json.JSONDecodeError:
            pass
            
    return user_data
