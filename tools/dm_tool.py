# tools/dm_tool.py
# -*- coding: utf-8 -*-

"""
A command-line tool for the Dungeon Master (DM) to review and rate
AI-generated story events. This helps curate high-quality data for
future model fine-tuning.
"""

import sys
import logging
from pathlib import Path
import textwrap

# Add the project root to the system path to allow imports from the 'class' package
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from class_folder.core.database_manager import DatabaseManager
except ImportError:
    logging.basicConfig()
    logging.critical("Could not import DatabaseManager. Make sure this script is in the project root or a subfolder.")
    sys.exit(1)

# Basic logging setup for the tool
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper functions for colored console output ---
def print_header(text):
    print("\n" + "="*80)
    print(f" {text}")
    print("="*80)

def print_player(text):
    # ANSI escape code for blue color
    print(f"\n\033[94m> Spieler:\033[0m\n{textwrap.fill(text, width=80)}")

def print_ai(text):
    # ANSI escape code for green color
    print(f"\n\033[92m> Spielleiter (KI):\033[0m\n{textwrap.fill(text, width=80)}")


def review_events():
    """
    Main function to start the event review process.
    """
    db_manager = DatabaseManager()
    
    try:
        events_to_review = db_manager.get_events_for_review(label='neutral')
    except Exception as e:
        logger.error(f"Failed to connect to the database or fetch events: {e}")
        return

    if not events_to_review:
        print("Keine neuen Ereignisse zum Bewerten gefunden. Alles ist auf dem neuesten Stand!")
        return

    print_header(f"{len(events_to_review)} Ereignisse warten auf eine Bewertung.")
    
    reviewed_count = 0
    for event in events_to_review:
        event_id = event['event_id']
        player_input = event['player_input']
        ai_output = event['ai_output']

        print_header(f"Bewerte Ereignis #{event_id}")
        print_player(player_input)
        print_ai(ai_output)

        while True:
            choice = input("\nBewertung: [g]ut (für Training), [s]chlecht (ignorieren), [ü]berspringen, [b]eenden -> ").lower()
            
            if choice == 'g':
                db_manager.update_event_quality(event_id, 'gut (Training)')
                print("\033[92m--> Als 'gut' markiert.\033[0m")
                reviewed_count += 1
                break
            elif choice == 's':
                db_manager.update_event_quality(event_id, 'schlecht (Ignorieren)')
                print("\033[91m--> Als 'schlecht' markiert.\033[0m")
                reviewed_count += 1
                break
            elif choice == 'ü':
                print("--> Übersprungen.")
                break
            elif choice == 'b':
                print("Bewertung beendet.")
                db_manager.close_connection()
                return
            else:
                print("Ungültige Eingabe. Bitte 'g', 's', 'ü' oder 'b' eingeben.")
    
    db_manager.close_connection()
    print("\n" + "="*80)
    print(f"Alle Ereignisse wurden durchgesehen. {reviewed_count} Ereignisse wurden bewertet.")
    print("="*80)


if __name__ == "__main__":
    review_events()
