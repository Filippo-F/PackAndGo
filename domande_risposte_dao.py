"""
domande_risposte_dao.py - Gestisce le operazioni sul database relative alle domande e risposte.
Permette ai viaggiatori di fare domande e ai coordinatori di rispondere.
"""

import sqlite3
import datetime

DB_PATH = "db/PackandGo.db"


def get_domande_by_proposta(id_proposta):
    """Restituisce tutte le domande (e risposte, se presenti) per una proposta di viaggio."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = '''SELECT * FROM domande_risposte WHERE id_proposta = ? ORDER BY data_domanda DESC'''  # Ordiniamo per data di domanda decrescente
    cursor.execute(sql, (id_proposta,))
    domande = cursor.fetchall()

    cursor.close()
    conn.close()

    return domande


def get_domanda_by_id(id_domanda):
    """Restituisce una domanda dato il suo ID. Utile per verificare a quale proposta appartiene."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = 'SELECT * FROM domande_risposte WHERE id = ?'
    cursor.execute(sql, (id_domanda,))
    domanda = cursor.fetchone()

    cursor.close()
    conn.close()

    return domanda


def add_domanda(id_viaggiatore, id_proposta, testo_domanda):
    """Aggiunge una domanda fatta da un viaggiatore su una proposta di viaggio."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Controllo: La proposta esiste?
    cursor.execute("SELECT id FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()
    if not proposta:
        return False, "Errore: La proposta non esiste."

    cursor.close()  
    cursor = conn.cursor()

    # Inseriamo la domanda nel database
    try:
        cursor.execute("INSERT INTO domande_risposte (id_viaggiatore, id_proposta, domanda, data_domanda) VALUES (?, ?, ?, ?)", 
                       (id_viaggiatore, id_proposta, testo_domanda, datetime.date.today()))
        conn.commit()
        success = True
    except Exception as e:
        print('Errore:', str(e))    # Il dettaglio dell'eccezione resta nel log del server e non viene mostrato all'utente
        conn.rollback()
        return False, "Errore nell'inserimento della domanda, riprova."

    cursor.close()
    conn.close()

    return success, "Domanda aggiunta con successo."


def rispondi_domanda(id_domanda, testo_risposta):
    """Permette al coordinatore di rispondere a una domanda."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Controllo: La domanda esiste ed è ancora senza risposta?
    cursor.execute("SELECT * FROM domande_risposte WHERE id = ? AND risposta IS NULL", (id_domanda,))
    domanda = cursor.fetchone()

    cursor.close()
    cursor = conn.cursor()

    if not domanda:
        return False, "Errore: La domanda non esiste o ha già una risposta."

    # Inseriamo la risposta nel database
    try:
        cursor.execute("UPDATE domande_risposte SET risposta = ?, data_risposta = ? WHERE id = ? AND risposta IS NULL",
                       (testo_risposta, datetime.date.today(), id_domanda))
        conn.commit()
        success = True
    except Exception as e:
        print('Errore:', str(e))    # Il dettaglio dell'eccezione resta nel log del server e non viene mostrato all'utente
        conn.rollback()
        return False, "Errore nell'inserimento della risposta, riprova."

    cursor.close()
    conn.close()

    return success, "Risposta aggiunta con successo."
