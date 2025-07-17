# server_tools/auth_utils.py
# -*- coding: utf-8 -*-

"""
Dieses Modul enthält Hilfsfunktionen für die Authentifizierung,
insbesondere für das Hashing und Verifizieren von Passwörtern.
"""

from passlib.context import CryptContext

# Wir definieren das Kryptographie-Schema.
# bcrypt ist ein starker und weit verbreiteter Algorithmus für Passwörter.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
