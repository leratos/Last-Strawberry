# server_tools/auth_utils.py
# -*- coding: utf-8 -*-

"""
Dieses Modul enthält Hilfsfunktionen für die Authentifizierung,
insbesondere für das Hashing und Verifizieren von Passwörtern sowie JWT-Token-Management.
"""

import jwt
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
from passlib.context import CryptContext

# Wir definieren das Kryptographie-Schema.
# bcrypt ist ein starker und weit verbreiteter Algorithmus für Passwörter.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT-Konfiguration
# In Produktion sollte dies aus Umgebungsvariablen geladen werden
SECRET_KEY = secrets.token_urlsafe(32)  # Generiert einen sicheren 32-Byte Schlüssel
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 Stunden

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Überprüft, ob ein Klartext-Passwort mit einem Hash übereinstimmt.
    
    Args:
        plain_password: Das vom Benutzer eingegebene Passwort.
        hashed_password: Das gespeicherte Hash-Passwort aus der Datenbank.

    Returns:
        True, wenn die Passwörter übereinstimmen, sonst False.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Erstellt einen Hash aus einem Klartext-Passwort.

    Args:
        password: Das zu hashende Passwort.

    Returns:
        Der resultierende Passwort-Hash als String.
    """
    return pwd_context.hash(password)

def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Erstellt einen JWT Access Token.
    
    Args:
        data: Die zu encodierenden Daten (username, roles, etc.)
        expires_delta: Optionale Ablaufzeit, defaults zu ACCESS_TOKEN_EXPIRE_MINUTES
    
    Returns:
        Der JWT Token als String
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        raise ValueError(f"Fehler beim Erstellen des JWT-Tokens: {e}")

def verify_access_token(token: str) -> Optional[Dict]:
    """
    Verifiziert und dekodiert einen JWT Access Token.
    
    Args:
        token: Der zu verifizierende JWT Token
    
    Returns:
        Die dekodierten Token-Daten oder None bei Fehlern
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token ist abgelaufen
    except jwt.InvalidTokenError:
        return None  # Token ist ungültig

def get_current_user_from_token(token: str) -> Optional[str]:
    """
    Extrahiert den Benutzernamen aus einem gültigen JWT Token.
    
    Args:
        token: Der JWT Token
    
    Returns:
        Der Benutzername oder None bei ungültigem Token
    """
    payload = verify_access_token(token)
    if payload:
        return payload.get("sub")  # "sub" (subject) enthält den Benutzernamen
    return None
