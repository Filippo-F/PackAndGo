"""
aggiorna_date_demo.py - Sposta in avanti le date dei dati demo, mantenendo le distanze tra una data e l'altra.

I dati demo sono stati creati in un giorno di riferimento (la data più recente tra prenotazioni e domande).
Lo script trasla tutte le date in modo che quel giorno diventi oggi: le proposte future restano prenotabili,
le bozze restano pubblicabili e la proposta "nel passato" resta nel passato. Si può rilanciare in qualsiasi momento.

Uso (dalla cartella del progetto): python aggiorna_date_demo.py
"""

import sqlite3
import datetime

DB_PATH = "db/PackandGo.db"

# Colonne con date in formato "anno-mese-giorno" (nomi fissi, non provenienti dall'utente)
COLONNE_DATA = {
    "proposte_viaggio": ["data_inizio", "data_fine"],
    "prenotazioni": ["data_prenotazione"],
    "domande_risposte": ["data_domanda", "data_risposta"],
}


def aggiorna_date():
    """Trasla tutte le date del database in modo che il giorno di riferimento coincida con oggi."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''SELECT MAX(data) FROM (
                          SELECT MAX(data_prenotazione) AS data FROM prenotazioni
                          UNION SELECT MAX(data_domanda) FROM domande_risposte
                      )''')
    riferimento = cursor.fetchone()[0]

    if not riferimento:
        print("Nessuna prenotazione o domanda nel database: impossibile calcolare il giorno di riferimento.")
        conn.close()
        return

    giorni = (datetime.date.today() - datetime.date.fromisoformat(riferimento)).days
    if giorni <= 0:
        print(f"Date già aggiornate (giorno di riferimento: {riferimento}).")
        conn.close()
        return

    for tabella, colonne in COLONNE_DATA.items():
        for colonna in colonne:
            # date(colonna, '+N days') è la funzione di SQLite per sommare giorni a una data
            cursor.execute(f"UPDATE {tabella} SET {colonna} = date({colonna}, ?) WHERE {colonna} IS NOT NULL", (f"+{giorni} days",))

    conn.commit()
    cursor.close()
    conn.close()

    print(f"Date spostate avanti di {giorni} giorni (giorno di riferimento {riferimento} -> {datetime.date.today()}).")


if __name__ == "__main__":
    aggiorna_date()
