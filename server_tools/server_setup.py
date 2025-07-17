# server_tools/server_setup.py
# -*- coding: utf-8 -*-

"""
Einmaliges Setup-Skript für den Server.
- Erstellt die Datenbank und alle Tabellen.
- Erstellt den ersten Admin-Benutzer (UserID=1).
"""

import sys
import getpass
from pathlib import Path

# Füge das Projektverzeichnis zum Python-Pfad hinzu
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from class_folder.core.database_manager import DatabaseManager
from server_tools.auth_utils import get_password_hash

def main():
    """Führt den Setup-Prozess aus."""
    print("--- Last-Strawberry Server Setup ---")
    
    db_manager = DatabaseManager()

    # 1. Datenbank und Tabellen erstellen
    try:
        print("1. Initialisiere Datenbank-Schema...")
        db_manager.setup_database()
        print("   ...Datenbank-Schema erfolgreich initialisiert.")
    except Exception as e:
        print(f"FEHLER: Konnte die Datenbank nicht initialisieren: {e}")
        return

    # 2. Prüfen, ob der Admin-Benutzer (UserID=1) bereits existiert
    admin_user = db_manager.get_user_by_id(1)
    if admin_user:
        print("\n2. Admin-Benutzer (UserID=1) existiert bereits. Setup wird übersprungen.")
    else:
        print("\n2. Erstelle initialen Admin-Benutzer (UserID=1)...")
        try:
            admin_username = input("   Geben Sie einen Benutzernamen für den Admin ein: ").strip()
            while True:
                admin_password = getpass.getpass("   Geben Sie ein sicheres Passwort für den Admin ein: ")
                password_confirm = getpass.getpass("   Passwort bestätigen: ")
                if admin_password == password_confirm:
                    break
                else:
                    print("   Die Passwörter stimmen nicht überein. Bitte erneut versuchen.")
            
            if not admin_username or not admin_password:
                print("FEHLER: Benutzername und Passwort dürfen nicht leer sein.")
                return

            # Passwort hashen
            hashed_password = get_password_hash(admin_password)
            
            # Benutzer in der Datenbank erstellen
            user_id = db_manager.create_user(
                username=admin_username,
                hashed_password=hashed_password,
                roles=["admin", "gamemaster"]
            )
            
            if user_id == 1:
                print("\n   Admin-Benutzer erfolgreich mit UserID=1 erstellt.")
            else:
                print(f"\n   WARNUNG: Admin-Benutzer wurde mit UserID={user_id} erstellt. Dies sollte 1 sein.")

        except Exception as e:
            print(f"FEHLER: Konnte den Admin-Benutzer nicht erstellen: {e}")
            return

    print("\n--- Setup abgeschlossen ---")


if __name__ == "__main__":
    main()
