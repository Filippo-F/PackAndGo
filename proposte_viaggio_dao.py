"""
proposte_viaggio_dao.py - Gestisce le operazioni sul database relative alle proposte di viaggio.
Permette ai coordinatori di creare, modificare, eliminare e ottenere viaggi.
"""

import sqlite3
import datetime
import os           # Per gestire i file


# Percorso assoluto del database: così l'app funziona anche se avviata da un'altra cartella (es. sul server di produzione)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "PackandGo.db")
CARTELLA_IMMAGINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads", "proposte")   # Anche qui percorso assoluto


def get_bozze_by_coordinatore(id_coordinatore):
    """Restituisce solo le proposte in bozza (stato = 0) di un coordinatore specifico."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = 'SELECT * FROM proposte_viaggio WHERE id_coordinatore = ? AND stato = 0'
    cursor.execute(sql, (id_coordinatore,))

    bozze = cursor.fetchall()
    cursor.close()
    conn.close()
    return bozze


def get_pubblicate_by_coordinatore(id_coordinatore):
    """Restituisce solo le proposte pubblicate (stato = 1) di un coordinatore specifico."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = 'SELECT * FROM proposte_viaggio WHERE id_coordinatore = ? AND stato = 1'
    cursor.execute(sql, (id_coordinatore,))

    pubblicate = cursor.fetchall()
    cursor.close()
    conn.close()    
    return pubblicate


def get_proposte_pubblicate():
    """Restituisce solo le proposte pubblicate, visibili ai viaggiatori, con data di inizio futura."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    data_oggi = datetime.date.today()

    # Solo proposte pubblicate con data inizio futura, sql gestisce le date in formato "anno-mese-giorno" quindi possiamo confrontarle direttamente e ordinare per data inizio crescente
    sql = 'SELECT * FROM proposte_viaggio WHERE stato = 1 AND data_inizio > ? ORDER BY data_inizio ASC'  

    cursor.execute(sql, (data_oggi,))
    proposte = cursor.fetchall()

    cursor.close()
    conn.close()

    return proposte


def get_proposta_by_id(id_proposta):
    """Restituisce una proposta specifica dato il suo ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = 'SELECT * FROM proposte_viaggio WHERE id = ?'
    cursor.execute(sql, (id_proposta,))
    proposta = cursor.fetchone()

    cursor.close()
    conn.close()

    return proposta


def add_proposta(proposta, immagine):
    """Aggiunge una nuova proposta di viaggio (solo per coordinatori)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    success = False
    sql = '''INSERT INTO proposte_viaggio (id_coordinatore, destinazione, data_inizio, data_fine, 
              num_massimo, descrizione, budget_trasporto, budget_alloggio, budget_attivita, stato, immagine) 
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

    try:
        cursor.execute(sql, (
            proposta['id_coordinatore'], 
            proposta['destinazione'], 
            proposta['data_inizio'], 
            proposta['data_fine'], 
            proposta['num_massimo'], 
            proposta['descrizione'], 
            proposta.get('budget_trasporto', None),     # Se non presente, budget_trasporto = None
            proposta.get('budget_alloggio', None),
            proposta.get('budget_attivita', None),
            0,                                          # La proposta è sempre una "bozza" quando viene creata (stato = 0)
            immagine                                    # Nome del file immagine caricato
        ))
        conn.commit()
        success = True
    except Exception as e:
        print('Errore:', str(e))
        conn.rollback()

    cursor.close()
    conn.close()

    return success


def update_proposta(id_proposta, dati_modificati, nuova_immagine):
    """Modifica una proposta di viaggio, mantenendo l'immagine attuale se non viene cambiata."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    cursor = conn.cursor()

    # Recuperiamo lo stato e l'immagine attuale della proposta
    cursor.execute("SELECT stato, immagine FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()

    if not proposta:
        print("Errore: La proposta non esiste.")
        cursor.close()
        conn.close()
        return False

    if proposta['stato'] == 1:
        print("Errore: La proposta è già pubblicata e non può essere modificata.")
        cursor.close()
        conn.close()
        return False

    # Determiniamo quale immagine utilizzare
    immagine_finale = nuova_immagine if nuova_immagine else proposta['immagine']

    # Se l'immagine cambia, eliminiamo la vecchia se non è la default
    if nuova_immagine and proposta['immagine'] and proposta['immagine'] != "default_travel_pic.jpg":
        percorso_immagine = os.path.join(CARTELLA_IMMAGINI, proposta['immagine'])
        if os.path.exists(percorso_immagine):
            os.remove(percorso_immagine)

    # Query per aggiornare la proposta
    sql = '''UPDATE proposte_viaggio SET 
             destinazione = ?, data_inizio = ?, data_fine = ?, num_massimo = ?, 
             descrizione = ?, budget_trasporto = ?, budget_alloggio = ?, budget_attivita = ?, 
             immagine = ? WHERE id = ?'''

    try:
        cursor.execute(sql, (
            dati_modificati['destinazione'], 
            dati_modificati['data_inizio'], 
            dati_modificati['data_fine'], 
            dati_modificati['num_massimo'], 
            dati_modificati['descrizione'], 
            dati_modificati.get('budget_trasporto', None),
            dati_modificati.get('budget_alloggio', None),
            dati_modificati.get('budget_attivita', None),
            immagine_finale,  
            id_proposta
        ))
        conn.commit()
        success = True
    except Exception as e:
        print('Errore:', str(e))
        conn.rollback()
        success = False

    cursor.close()
    conn.close()

    return success



def delete_proposta(id_proposta):
    """Elimina una proposta di viaggio solo se è ancora in bozza."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Recuperiamo l'immagine della proposta prima di eliminarla
    cursor.execute("SELECT immagine FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()

    immagine = proposta["immagine"]

    cursor.close()
    cursor = conn.cursor()
    
    # Controlliamo se la proposta è ancora in bozza
    cursor.execute("SELECT stato FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()

    if not proposta or proposta['stato'] == 1:  
        print("Errore: La proposta è già pubblicata e non può essere eliminata.")
        return False

    sql = "DELETE FROM proposte_viaggio WHERE id = ?"

    try:
        cursor.execute(sql, (id_proposta,))
        conn.commit()
        success = True

        # Se la proposta aveva un'immagine diversa da quella di default, la eliminiamo
        if immagine and immagine != "default_travel_pic.jpg":
            percorso_immagine = os.path.join(CARTELLA_IMMAGINI, immagine)
            if os.path.exists(percorso_immagine):
                os.remove(percorso_immagine)
                
    except Exception as e:
        print('Errore:', str(e))
        conn.rollback()
        success = False

    cursor.close()
    conn.close()

    return success


def pubblica_proposta(id_proposta):
    """Pubblica una proposta di viaggio, se non ha date nel passato."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Controlliamo le date della proposta
    cursor.execute("SELECT data_inizio FROM proposte_viaggio WHERE id = ?", (id_proposta,))
    proposta = cursor.fetchone()

    cursor.close()  
    cursor = conn.cursor()

    if not proposta:
        print("Errore: La proposta non esiste.")
        return False

    data_oggi = datetime.date.today()                   # Data odierna senza orario
    data_inizio = datetime.datetime.strptime(proposta['data_inizio'], "%Y-%m-%d").date()   # Convertiamo la data inizio in formato datetime "anno-mese-giorno" e prendiamo solo la data con ".date()"

    if data_inizio < data_oggi:
        print("Errore: Non puoi pubblicare una proposta con date nel passato.")
        return False

    # Se tutto è corretto, aggiorniamo lo stato della proposta
    sql = "UPDATE proposte_viaggio SET stato = 1 WHERE id = ?"

    try:
        cursor.execute(sql, (id_proposta,))
        conn.commit()
        success = True
    except Exception as e:
        print('Errore:', str(e))
        conn.rollback()
        success = False

    cursor.close()
    conn.close()

    return success