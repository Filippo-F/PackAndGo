"""
prenotazioni_dao.py - Gestisce le operazioni sul database relative alle prenotazioni.
Permette ai viaggiatori di prenotarsi ai viaggi, rispettando le regole di disponibilità.
"""

import sqlite3
import os
import datetime

# Percorso assoluto del database: così l'app funziona anche se avviata da un'altra cartella (es. sul server di produzione)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "PackandGo.db")


def get_prenotazioni_by_viaggiatore(id_viaggiatore):
    """Restituisce tutte le prenotazioni effettuate da un viaggiatore."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = '''SELECT * FROM prenotazioni WHERE id_viaggiatore = ?'''
    cursor.execute(sql, (id_viaggiatore,))
    prenotazioni = cursor.fetchall()

    cursor.close()
    conn.close()

    return prenotazioni


def get_posti_disponibili(id_proposta):
    """Restituisce il numero di posti ancora disponibili per una proposta di viaggio."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Otteniamo il numero massimo di partecipanti per il viaggio
    cursor.execute("SELECT num_massimo FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()

    cursor.close()  
    cursor = conn.cursor()

    if not proposta:
        return None  # La proposta non esiste

    num_massimo = proposta["num_massimo"]

    # Contiamo quante prenotazioni esistono già per questa proposta
    cursor.execute("SELECT COUNT(*) as prenotati FROM prenotazioni WHERE id_proposta = ?", (id_proposta,))  # prenotati = numero di prenotazioni già effettuate
    prenotati = cursor.fetchone()["prenotati"]    
    
    posti_disponibili = num_massimo - prenotati

    cursor.close()
    conn.close()

    return posti_disponibili


def get_partecipanti_by_proposta(id_proposta):
    """Restituisce l'elenco dei partecipanti per una proposta di viaggio dato il suo ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = '''
        SELECT utenti.id, utenti.username, utenti.immagine_profilo
        FROM prenotazioni
        JOIN utenti ON prenotazioni.id_viaggiatore = utenti.id
        WHERE prenotazioni.id_proposta = ?
    '''  # Seleziona l'id, il nome utente e l'immagine profilo degli utenti che hanno prenotato il viaggio con l'id passato come parametro
    
    cursor.execute(sql, (id_proposta,))
    partecipanti = cursor.fetchall()

    cursor.close()
    conn.close()

    return partecipanti


def add_prenotazione(id_viaggiatore, id_proposta):
    """Effettua una prenotazione per un viaggiatore, rispettando i controlli."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Controllo: Il viaggio esiste?
    cursor.execute("SELECT data_inizio, data_fine, num_massimo, stato FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()
    if not proposta:
        return False, "Errore: Il viaggio non esiste."

    # Controllo: Il viaggio è pubblicato? Le bozze (stato = 0) non sono prenotabili
    if proposta["stato"] != 1:
        return False, "Errore: Il viaggio non esiste."

    # Controllo: Il viaggio deve ancora iniziare? Stesso criterio usato per mostrare le proposte ai viaggiatori
    if proposta["data_inizio"] <= datetime.date.today().isoformat():    # Le date "anno-mese-giorno" si possono confrontare come stringhe
        return False, "Errore: Non è più possibile prenotare questo viaggio."

    cursor.close()
    cursor = conn.cursor()

    data_inizio = proposta["data_inizio"]  # Salviamo le date di inizio e fine del viaggio che ci serviranno per i controlli delle sovrapposizioni di date
    data_fine = proposta["data_fine"]

    # Controllo: Ci sono posti disponibili?
    cursor.execute("SELECT COUNT(*) as prenotati FROM prenotazioni WHERE id_proposta = ?", (id_proposta,))  
    prenotati = cursor.fetchone()["prenotati"]

    cursor.close()
    cursor = conn.cursor()

    if prenotati >= proposta["num_massimo"]:
        return False, "Errore: Non ci sono posti disponibili per questo viaggio."

    # Controllo: Il viaggiatore ha già prenotato questo viaggio?
    cursor.execute("SELECT * FROM prenotazioni WHERE id_viaggiatore = ? AND id_proposta = ?", (id_viaggiatore, id_proposta))
    prenotazione_esistente = cursor.fetchone()
    if prenotazione_esistente:
        return False, "Errore: Sei già prenotato per questo viaggio."

    cursor.close()
    cursor = conn.cursor()

    # Controllo: Il viaggiatore ha già un altro viaggio nelle stesse date?
    # Seleziona le date unendo la tabella delle prenotazioni con quella dei viaggi in base all'id_proposta, dove l'id_viaggiatore è uguale all'id_viaggiatore passato come parametro e le date si sovrappongono
    cursor.execute("""
        SELECT p.destinazione, p.data_inizio, p.data_fine 
        FROM prenotazioni pr
        JOIN proposte_viaggio p ON pr.id_proposta = p.id
        WHERE pr.id_viaggiatore = ? 
        AND (
            (p.data_inizio <= ? AND p.data_fine >= ?)  -- Sovrapposizione con l'inizio del nuovo viaggio
            OR 
            (p.data_inizio <= ? AND p.data_fine >= ?)  -- Sovrapposizione con la fine del nuovo viaggio
            OR 
            (p.data_inizio >= ? AND p.data_fine <= ?)  -- Il nuovo viaggio copre completamente un altro viaggio
        )
    """, (id_viaggiatore, data_fine, data_fine, data_inizio, data_inizio, data_inizio, data_fine))  

    sovrapposizione = cursor.fetchone()
    if sovrapposizione:
        return False, f"Errore: Hai già un altro viaggio prenotato a {sovrapposizione['destinazione']} dal {sovrapposizione['data_inizio']} al {sovrapposizione['data_fine']}."

    cursor.close()
    cursor = conn.cursor()
    
    # Effettuiamo la prenotazione
    try:
        cursor.execute("INSERT INTO prenotazioni (id_viaggiatore, id_proposta, data_prenotazione) VALUES (?, ?, ?)", 
                       (id_viaggiatore, id_proposta, datetime.date.today()))
        conn.commit()
        success = True
    except Exception as e:
        print('Errore:', str(e))    # Il dettaglio dell'eccezione resta nel log del server e non viene mostrato all'utente
        conn.rollback()
        return False, "Errore nella prenotazione, riprova."

    cursor.close()
    conn.close()

    return success, "Prenotazione effettuata con successo!"
