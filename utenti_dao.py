"""
utenti_dao.py - "Data access Object" che gestisce le operazioni sul database relative agli utenti.
Include funzioni per aggiungere e recuperare utenti.
"""

import sqlite3

DB_PATH = "db/PackandGo.db"


def add_user(user):
    """Aggiunge un nuovo utente al database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    success = False
    sql = 'INSERT INTO utenti(username, password, tipo_utente, nome, immagine_profilo) VALUES(?,?,?,?,?)'

    # Se l'utente è un coordinatore (1), il nome deve essere obbligatorio
    nome = user.get('nome', None) if user['tipo_utente'] == 1 else None  # get() restituisce "nome" se presente, altrimenti None

    try:
        cursor.execute(sql, (
            user['username'], 
            user['password'], 
            user['tipo_utente'],                 # 0 = Viaggiatore, 1 = Coordinatore
            nome,                                # Nome inserito solo se coordinatore
            user.get('immagine_profilo', None)   # Se non presente, immagine_profilo = None
        ))    
        conn.commit()  
        success = True
    except Exception as e:      
        print('Errore:', str(e)) 
        conn.rollback()                          # Annulla la transazione in caso di errore

    cursor.close()
    conn.close()

    return success


def get_user_by_id(id):
    """Restituisce un utente dato il suo ID. Utile per Flask-Login."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = 'SELECT * FROM utenti WHERE id = ?'   # Query che prende tutti i campi dell'utente con l'id specificato
    cursor.execute(sql, (id,))                  # Cursor.execute() accetta una tupla come secondo argomento quindi (id,) è una tupla con un solo elemento, per questo serve la virgola
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return user


def get_user_by_username(username):
    """Restituisce un utente dato il suo username. Utile per login e registrazione."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = 'SELECT * FROM utenti WHERE username = ?'
    cursor.execute(sql, (username,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return user
