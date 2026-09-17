"""
app.py - Configura Flask, Flask-Login e gestisce l'autenticazione utenti.
Include le funzioni per la gestione delle pagine del sito, delle proposte di viaggio, delle prenotazioni, delle domande-risposte e delle immagini.
"""

from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from functools import wraps

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename   # Per evitare attacchi nel caso in cui il nome del file contenga caratteri speciali che potrebbero essere interpretati come path dal sistema operativo
import datetime, time, os, secrets, json

from PIL import Image   # Pillow - Python Imaging Library used to pre-process images before saving them to the server

import utenti_dao, proposte_viaggio_dao, prenotazioni_dao, domande_risposte_dao
from models import User

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")   # Percorso assoluto: il salvataggio delle immagini non dipende dalla cartella di avvio
PROFILE_FOLDER = "profili"         # Sottocartella per le immagini profilo
TRIP_FOLDER = "proposte"  # Sottocartella per le immagini delle proposte
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
PROFILE_IMG_SIZE = 100  # Thumbnail 100x100 px
MAX_WIDTH = 1200  # Massima larghezza immagine proposta (nitida anche su schermi ad alta densità)
MAX_HEIGHT = 900  # Massima altezza immagine proposta
MAX_BUDGET = 100_000_000  # Valore massimo di ogni voce di budget, uguale al limite dei campi nel form
MAX_UPLOAD_MB = 10  # Dimensione massima di una richiesta con upload, oltre Flask risponde con errore 413
MAX_IMAGE_PIXELS = 50_000_000  # Massimo 50 megapixel: evita immagini piccole su disco ma enormi una volta decompresse
ERRORI_IMMAGINE = (OSError, ValueError, Image.DecompressionBombError)  # Errori di Pillow per file non validi o troppo grandi
CAMPI_NON_CONSERVATI = {"password", "password_confirm", "csrf_token"}  # Mai salvati nella sessione: il cookie è firmato ma non cifrato
MAX_BYTE_CONSERVATI = 2000  # Spazio massimo per i dati conservati: il cookie di sessione non può superare circa 4 KB


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024   # Limite in byte

# La chiave segreta firma i cookie di sessione: va letta da variabile d'ambiente e non scritta nel codice
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    # Fallback solo per lo sviluppo locale: chiave casuale diversa a ogni avvio (le sessioni non sopravvivono al riavvio)
    app.secret_key = secrets.token_hex(32)
    print("ATTENZIONE: SECRET_KEY non impostata, uso una chiave temporanea valida solo per lo sviluppo locale.")

# Protezione CSRF: tutte le richieste POST devono contenere un token valido generato dal server
csrf = CSRFProtect(app)

# Configurazione Flask-Login
login_manager = LoginManager()       # Crea un oggetto di tipo LoginManager
login_manager.init_app(app)          # Inizializza l'applicazione Flask
login_manager.login_view = "home"   # Se un utente non autenticato prova ad accedere a una pagina protetta, viene reindirizzato alla pagina "/home"

@app.errorhandler(CSRFError)
def csrf_error(e):
    """Gestisce le richieste POST con token CSRF mancante, scaduto o non valido."""
    flash("Richiesta non valida o sessione scaduta, riprova.", "danger")
    return redirect(url_for('home'))

@app.errorhandler(413)
def file_troppo_grande(e):
    """Gestisce le richieste che superano MAX_CONTENT_LENGTH."""
    flash(f"Errore: File troppo grande, la dimensione massima è {MAX_UPLOAD_MB} MB.", "danger")
    return redirect(url_for('home'))


"""
Conservazione dei dati dei form rifiutati
"""


def conta_errori_flash():
    """Conta i messaggi flash di errore (categoria "danger") in attesa di essere mostrati."""
    return sum(1 for categoria, _ in session.get('_flashes', []) if categoria == 'danger')


def conserva_form_se_errore(form, modale=None):
    """Decoratore per le route che ricevono un form: se la route aggiunge un messaggio di errore, salva nella sessione
    i dati inviati (tranne password e token), così dopo il redirect il template ripopola i campi e riapre il modale.
    "form" identifica il form e "modale" è l'id HTML del modale da riaprire (se diverso da "form");
    entrambi possono contenere parametri della route, es. "modificaPropostaModal{id_proposta}"."""
    def decoratore(funzione):
        @wraps(funzione)
        def wrapper(*args, **kwargs):
            errori_prima = conta_errori_flash()
            risposta = funzione(*args, **kwargs)

            if conta_errori_flash() > errori_prima:
                dati = {}
                spazio_usato = 0
                for campo, valore in request.form.items():
                    if campo in CAMPI_NON_CONSERVATI:
                        continue
                    dimensione = len(json.dumps(valore))    # Dimensione del valore come verrà scritto nel cookie
                    if spazio_usato + dimensione > MAX_BYTE_CONSERVATI:
                        continue    # Un campo troppo grande non viene conservato: meglio un campo vuoto che un cookie scartato dal browser
                    dati[campo] = valore
                    spazio_usato += dimensione

                session['form_precedente'] = {
                    'form': form.format(**kwargs),
                    'modale': (modale or form).format(**kwargs),
                    'dati': dati
                }
            return risposta
        return wrapper
    return decoratore


@app.context_processor
def dati_form_precedente():
    """Rende disponibili ai template i dati dell'ultimo form rifiutato. Vengono letti una sola volta, come i messaggi flash."""
    form_precedente = session.pop('form_precedente', None)

    def valore_form(form, campo, predefinito=''):
        """Restituisce il valore inviato prima dell'errore se "form" è il form rifiutato, altrimenti il valore predefinito."""
        if form_precedente and form_precedente['form'] == form:
            return form_precedente['dati'].get(campo, predefinito)
        return predefinito

    return {'form_precedente': form_precedente, 'valore_form': valore_form}

 
"""
Gestione delle pagine relative al sito
"""


@app.route('/')
def home():
    """Mostra la home page o reindirizza alla dashboard se l'utente è loggato."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))  # Reindirizza i loggati alla dashboard
    return render_template('home.html')  # Mostra la home solo ai non loggati

@app.route('/dashboard')
@login_required
def dashboard():
    """Reindirizza alla dashboard corretta in base al tipo di utente."""
    if current_user.tipo_utente == 1:  # Coordinatore
        bozze = proposte_viaggio_dao.get_bozze_by_coordinatore(current_user.id)
        pubblicate = proposte_viaggio_dao.get_pubblicate_by_coordinatore(current_user.id)
        prenotazioni = prenotazioni_dao.get_prenotazioni_by_viaggiatore(current_user.id)

        return render_template('coordinatore.html', bozze=bozze, pubblicate=pubblicate, prenotazioni=prenotazioni)

    elif current_user.tipo_utente == 0:  # Viaggiatore
        proposte_raw = proposte_viaggio_dao.get_proposte_pubblicate()
        prenotazioni_utente = [p['id_proposta'] for p in prenotazioni_dao.get_prenotazioni_by_viaggiatore(current_user.id)]

        proposte = []   # Lista di proposte da passare al template

        for proposta in proposte_raw:
            # Otteniamo il numero di posti disponibili
            posti_disponibili = prenotazioni_dao.get_posti_disponibili(proposta['id'])

            # Recuperiamo le informazioni del coordinatore
            coordinatore = utenti_dao.get_user_by_id(proposta['id_coordinatore'])

            proposte.append({
                "id": proposta['id'],
                "destinazione": proposta['destinazione'],
                "data_inizio": proposta['data_inizio'],
                "data_fine": proposta['data_fine'],
                "posti_disponibili": posti_disponibili,  
                "budget_trasporto": proposta['budget_trasporto'],
                "budget_alloggio": proposta['budget_alloggio'],
                "budget_attivita": proposta['budget_attivita'],
                "descrizione": proposta['descrizione'],
                "immagine": proposta['immagine'],
                "coordinatore_username": coordinatore['username'],
                "immagine_profilo": coordinatore['immagine_profilo'],
                "prenotato": proposta['id'] in prenotazioni_utente  # True se il viaggiatore ha prenotato
            })

        return render_template('viaggiatore.html', proposte=proposte)

    flash("Errore: Tipo utente non riconosciuto.", "danger")
    return redirect(url_for('home'))


@app.route('/proposta/<int:id_proposta>')
@login_required
def proposta(id_proposta):
    """Mostra i dettagli di una proposta di viaggio, disponibile sia per viaggiatori che per coordinatori."""
    
    proposta = proposte_viaggio_dao.get_proposta_by_id(id_proposta)
    
    if not proposta:
        flash("Errore: La proposta richiesta non esiste.", "danger")
        return redirect(url_for('dashboard'))

    # True solo se l'utente è il coordinatore che ha creato la proposta
    is_proprietario = current_user.tipo_utente == 1 and proposta['id_coordinatore'] == current_user.id

    # Le bozze sono visibili solo al proprietario: agli altri utenti rispondiamo come se la proposta non esistesse
    if proposta['stato'] == 0 and not is_proprietario:
        flash("Errore: La proposta richiesta non esiste.", "danger")
        return redirect(url_for('dashboard'))

    # Se l'utente è un viaggiatore, otteniamo il numero di posti disponibili
    posti_disponibili = prenotazioni_dao.get_posti_disponibili(id_proposta) if current_user.tipo_utente == 0 else None

    # Solo il coordinatore proprietario può vedere l'elenco dei partecipanti
    partecipanti = prenotazioni_dao.get_partecipanti_by_proposta(id_proposta) if is_proprietario else []

    # Recuperiamo le domande con i dati degli utenti
    domande_raw = domande_risposte_dao.get_domande_by_proposta(id_proposta)

    # Se l'utente è viaggiatore, controlliamo se l'utente ha prenotato questa proposta
    prenotato = id_proposta in [p['id_proposta'] for p in prenotazioni_dao.get_prenotazioni_by_viaggiatore(current_user.id)] if current_user.tipo_utente == 0 else None
    
    domande = []
    for domanda in domande_raw:
        utente = utenti_dao.get_user_by_id(domanda["id_viaggiatore"])  # Recupera i dati dell'utente
        coordinatore = utenti_dao.get_user_by_id(proposta["id_coordinatore"])  # Dati del coordinatore

        domande.append({
            "id": domanda["id"],
            "domanda": domanda["domanda"],  
            "risposta": domanda["risposta"] if domanda["risposta"] else None,               # Se non c'è risposta, passa None
            "data_domanda": domanda["data_domanda"],
            "data_risposta": domanda["data_risposta"] if domanda["risposta"] else None,     # Se non c'è risposta, passa None
            "username_utente": utente["username"] if utente else "Utente Sconosciuto",
            "immagine_utente": utente["immagine_profilo"] if utente and utente["immagine_profilo"] else "default_pro_pic.jpg",
            "username_coordinatore": coordinatore["username"] if coordinatore else "Coordinatore Sconosciuto",
            "immagine_coordinatore": coordinatore["immagine_profilo"] if coordinatore and coordinatore["immagine_profilo"] else "default_pro_pic.jpg"
        })

    return render_template('proposta.html', proposta=proposta, partecipanti=partecipanti, domande=domande, posti_disponibili=posti_disponibili, prenotato=prenotato, is_proprietario=is_proprietario)


"""
Gestione delle proposte di viaggio
"""


def converti_budget(valore):
    """Converte una voce di budget del form: None se vuota, altrimenti un numero tra 0 e MAX_BUDGET arrotondato a 2 decimali.
    Solleva ValueError se il valore non è valido."""
    if not valore:
        return None
    numero = float(valore)                  # ValueError se non è un numero (es. "abc")
    if not 0 <= numero <= MAX_BUDGET:       # Esclude anche i negativi, "nan" e "inf"
        raise ValueError("Budget fuori intervallo")
    return round(numero, 2)                 # "round" arrotonda il valore a 2 decimali



@app.route('/nuova_proposta', methods=['POST'])
@login_required
@conserva_form_se_errore('aggiungiPropostaModal')
def nuova_proposta():
    """Permette ai coordinatori di creare una nuova proposta di viaggio."""
    if current_user.tipo_utente != 1:     # Non necessario ma aggiunto per sicurezza maggiore in caso di Html manipulation
        flash("Accesso negato: questa operazione è riservata ai coordinatori.", "danger")
        return redirect(url_for('home'))

    dati_proposta = request.form.to_dict()
    dati_proposta['id_coordinatore'] = current_user.id

    # Controllo che i campi essenziali non siano vuoti, già gestito in frontend ma aggiungiamo un controllo in caso l'utente invii una richiesta HTTP personalizzata bypassando la restrizione nel frontend
    campi_obbligatori = ["destinazione", "data_inizio", "data_fine", "descrizione", "num_massimo"]
    for campo in campi_obbligatori:
        if not dati_proposta.get(campo):
            flash(f"Errore: il campo '{campo}' è obbligatorio.", "danger")
            return redirect(url_for('dashboard'))

    # Controllo validità delle date
    try:
        data_inizio = datetime.datetime.strptime(dati_proposta['data_inizio'], "%Y-%m-%d").date()   # Converte la data in formato stringa in un oggetto datetime.date ovvero data senza orario
        data_fine = datetime.datetime.strptime(dati_proposta['data_fine'], "%Y-%m-%d").date()

        if data_fine < data_inizio:
            flash("Errore: la data di fine deve essere successiva alla data di inizio.", "danger")
            return redirect(url_for('dashboard'))
    except ValueError:
        flash("Errore: formato data non valido.", "danger")
        return redirect(url_for('dashboard'))

    # Controllo validità di num_massimo
    try:
        dati_proposta['num_massimo'] = int(dati_proposta['num_massimo'])
        if dati_proposta['num_massimo'] <= 0:
            flash("Errore: Il numero massimo di partecipanti deve essere maggiore di zero.", "danger")
            return redirect(url_for('dashboard'))
    except ValueError:
        flash("Errore: Il numero massimo di partecipanti deve essere un numero intero.", "danger")
        return redirect(url_for('dashboard'))

    # Conversione dei campi numerici opzionali
    try:
        for campo in ("budget_trasporto", "budget_alloggio", "budget_attivita"):
            dati_proposta[campo] = converti_budget(dati_proposta.get(campo))
    except ValueError:
        flash("Errore: Ogni voce di budget deve essere un numero tra 0 e 100.000.000.", "danger")
        return redirect(url_for('dashboard'))


    # Controllo sulla lunghezza della destinazione (stesso limite del form)
    if len(dati_proposta['destinazione']) > 100:
        flash("Errore: La destinazione non può superare i 100 caratteri.", "danger")
        return redirect(url_for('dashboard'))

    # Controllo sulla lunghezza della descrizione
    if len(dati_proposta['descrizione']) > 1000:
        flash("Errore: La descrizione non può superare i 1000 caratteri.", "danger")  # Come da specifiche
        return redirect(url_for('dashboard'))

    # Gestione immagine proposta
    trip_image = request.files.get('immagine_proposta')   # Uso .get() per evitare errori perché se l'utente non carica un'immagine, il valore sarà None
    #Aggiungiamo un controllo in caso l'utente invii una richiesta HTTP personalizzata bypassando la restrizione nel frontend
    if trip_image and trip_image.filename != "":
        if not allowed_file(trip_image.filename):  # Controllo formato file
            flash("Formato immagine non supportato. Usa solo PNG, JPG o JPEG.", "danger")
            return redirect(url_for('dashboard'))
        try:
            immagine = process_trip_image(trip_image, dati_proposta['id_coordinatore'])
        except ERRORI_IMMAGINE:
            flash("Errore: Immagine non valida o troppo grande.", "danger")
            return redirect(url_for('dashboard'))
    else:
        immagine = "default_travel_pic.jpg"  # Assegna l'immagine predefinita

    success = proposte_viaggio_dao.add_proposta(dati_proposta, immagine)

    if success:
        flash("Proposta di viaggio creata con successo!", "success")
    else:
        flash("Errore nella creazione della proposta.", "danger")
        
    return redirect(url_for('dashboard'))


@app.route('/proposta_modifica/<int:id_proposta>', methods=['POST'])     # "int:id_proposta" è usato per passare l'id della proposta da modificare alla funzione modifica_proposta
@login_required 
@conserva_form_se_errore('modificaPropostaModal{id_proposta}')
def modifica_proposta(id_proposta):
    """Permette ai coordinatori di modificare una proposta di viaggio (solo se in bozza)."""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: questa operazione è riservata ai coordinatori.", "danger")
        return redirect(url_for('home'))
    
    proposta = proposte_viaggio_dao.get_proposta_by_id(id_proposta)
    if not proposta or proposta['id_coordinatore'] != current_user.id:
        flash("Errore: La proposta non esiste o non è di tua proprietà.", "danger")
        return redirect(url_for('dashboard'))

    if proposta['stato'] == 1:
        flash("Errore: La proposta è già pubblicata e non può essere modificata.", "danger")
        return redirect(url_for('dashboard'))
    
    dati_proposta = request.form.to_dict()

    # Controllo che i campi essenziali non siano vuoti (prima di tutti gli altri controlli che li usano)
    campi_obbligatori = ["destinazione", "data_inizio", "data_fine", "descrizione", "num_massimo"]
    for campo in campi_obbligatori:
        if not dati_proposta.get(campo):
            flash(f"Errore: il campo '{campo}' è obbligatorio.", "danger")
            return redirect(url_for('dashboard'))

    # Controllo sulla lunghezza della destinazione (stesso limite del form)
    if len(dati_proposta['destinazione']) > 100:
        flash("Errore: La destinazione non può superare i 100 caratteri.", "danger")
        return redirect(url_for('dashboard'))

    # Controllo sulla lunghezza della descrizione
    if len(dati_proposta['descrizione']) > 1000:
        flash("Errore: La descrizione non può superare i 1000 caratteri.", "danger")
        return redirect(url_for('dashboard'))

    # Controllo validità delle date
    try:
        data_inizio = datetime.datetime.strptime(dati_proposta['data_inizio'], "%Y-%m-%d").date()
        data_fine = datetime.datetime.strptime(dati_proposta['data_fine'], "%Y-%m-%d").date()

        if data_fine < data_inizio:
            flash("Errore: la data di fine deve essere successiva alla data di inizio.", "danger")
            return redirect(url_for('dashboard'))
    except ValueError:
        flash("Errore: formato data non valido.", "danger")
        return redirect(url_for('dashboard'))

    # Controllo validità di num_massimo
    try:
        dati_proposta['num_massimo'] = int(dati_proposta['num_massimo'])
        if dati_proposta['num_massimo'] <= 0:
            flash("Errore: Il numero massimo di partecipanti deve essere maggiore di zero.", "danger")
            return redirect(url_for('dashboard'))
    except ValueError:
        flash("Errore: Il numero massimo di partecipanti deve essere un numero intero.", "danger")
        return redirect(url_for('dashboard'))

    # Conversione dei campi numerici opzionali
    try:
        for campo in ("budget_trasporto", "budget_alloggio", "budget_attivita"):
            dati_proposta[campo] = converti_budget(dati_proposta.get(campo))
    except ValueError:
        flash("Errore: Ogni voce di budget deve essere un numero tra 0 e 100.000.000.", "danger")
        return redirect(url_for('dashboard'))

    # Gestione immagine proposta: elaborata solo dopo tutti i controlli, così un form non valido non lascia file inutilizzati sul disco
    nuova_immagine = request.files.get('immagine_proposta')  # Prendiamo direttamente il file

    # Se non viene caricata una nuova immagine, passiamo None
    immagine = None
    if nuova_immagine and nuova_immagine.filename.strip():
        if not allowed_file(nuova_immagine.filename):
            flash("Formato immagine non supportato. Usa solo PNG, JPG o JPEG.", "danger")
            return redirect(url_for('dashboard'))
        try:
            immagine = process_trip_image(nuova_immagine, proposta['id_coordinatore'])
        except ERRORI_IMMAGINE:
            flash("Errore: Immagine non valida o troppo grande.", "danger")
            return redirect(url_for('dashboard'))

    success = proposte_viaggio_dao.update_proposta(id_proposta, dati_proposta, immagine)

    if success:
        flash("Proposta aggiornata con successo!", "success")
    else:
        flash("Errore: la proposta è già pubblicata o non esiste.", "danger")   

    return redirect(url_for('dashboard'))


@app.route('/elimina_proposta/<int:id_proposta>', methods=['POST'])
@login_required
def elimina_proposta(id_proposta):
    """Permette ai coordinatori di eliminare una proposta di viaggio (solo se in bozza e di loro proprietà)"""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: Solo i coordinatori possono eliminare proposte.", "danger")
        return redirect(url_for('dashboard'))
    
    proposta = proposte_viaggio_dao.get_proposta_by_id(id_proposta)
    if not proposta or proposta['id_coordinatore'] != current_user.id:
        flash("Errore: La proposta non esiste o non è di tua proprietà.", "danger")
        return redirect(url_for('dashboard'))

    if proposta['stato'] == 1:
        flash("Errore: Non puoi eliminare una proposta già pubblicata.", "danger")
        return redirect(url_for('dashboard'))

    success = proposte_viaggio_dao.delete_proposta(id_proposta)

    if success:
        flash("Proposta eliminata con successo!", "success")
    else:
        flash("Errore: la proposta non esiste.", "danger") 

    return redirect(url_for('dashboard'))


@app.route('/conferma_pubblicazione/<int:id_proposta>', methods=['POST'])
@login_required
def conferma_pubblicazione(id_proposta):
    """Permette ai coordinatori di pubblicare una proposta di viaggio (solo se in bozza e di loro proprietà)."""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: Solo i coordinatori possono pubblicare proposte.", "danger")
        return redirect(url_for('dashboard'))
    
    proposta = proposte_viaggio_dao.get_proposta_by_id(id_proposta)
    if not proposta or proposta['id_coordinatore'] != current_user.id:
        flash("Errore: La proposta non esiste o non è di tua proprietà.", "danger")
        return redirect(url_for('dashboard'))

    if proposta['stato'] == 1:
        flash("Errore: Questa proposta è già stata pubblicata.", "danger")
        return redirect(url_for('dashboard'))
    
    # Controllo se la data di inizio è nel passato
    data_oggi = datetime.date.today()
    data_inizio = datetime.datetime.strptime(proposta['data_inizio'], "%Y-%m-%d").date()

    if data_inizio < data_oggi:
        flash("Errore: Non puoi pubblicare una proposta con data di inizio nel passato.", "danger")
        return redirect(url_for('dashboard'))

    success = proposte_viaggio_dao.pubblica_proposta(id_proposta)

    if success:
        flash("Proposta pubblicata con successo!", "success")
    else:
        flash("Errore: la proposta non esiste.", "danger") 

    return redirect(url_for('dashboard'))


"""
Gestione delle prenotazioni
"""


@app.route('/prenota/<int:id_proposta>', methods=['POST'])
@login_required
def prenota_viaggio(id_proposta):
    """Permette ai viaggiatori di prenotare un viaggio."""
    if current_user.tipo_utente != 0:  
        flash("Accesso negato: Solo i viaggiatori possono effettuare prenotazioni.", "danger")
        return redirect(url_for('home'))

    success, message = prenotazioni_dao.add_prenotazione(current_user.id, id_proposta)

    if success:
        flash("Prenotazione effettuata con successo!", "success")
    else:   
        flash(message, "danger")
    
    return redirect(url_for('proposta', id_proposta=id_proposta))  


"""
Gestione delle domande e risposte
"""


@app.route('/domande_aggiungi/<int:id_proposta>', methods=['POST'])
@login_required
@conserva_form_se_errore('confirmQuestionModal')
def aggiungi_domanda(id_proposta):
    """Permette ai viaggiatori di fare una domanda su una proposta."""
    if current_user.tipo_utente != 0:
        flash("Accesso negato: Solo i viaggiatori possono fare domande.", "danger")
        return redirect(url_for('dashboard'))

    # Si possono fare domande solo su proposte pubblicate: le bozze vengono trattate come inesistenti
    proposta = proposte_viaggio_dao.get_proposta_by_id(id_proposta)
    if not proposta or proposta['stato'] != 1:
        flash("Errore: La proposta richiesta non esiste.", "danger")
        return redirect(url_for('dashboard'))

    testo_domanda = request.form.get("testo_domanda")
    
    if not testo_domanda:
        flash("Errore: Il testo della domanda non può essere vuoto.", "danger")
        return redirect(url_for('proposta', id_proposta=id_proposta)) 

    # Il DAO restituisce una coppia (esito, messaggio): va separata, altrimenti la tupla risulta sempre "vera"
    success, message = domande_risposte_dao.add_domanda(current_user.id, id_proposta, testo_domanda)

    if success:
        flash("Domanda inviata con successo!", "success")
    else:
        flash(message, "danger")

    return redirect(url_for('proposta', id_proposta=id_proposta))



@app.route('/domande_rispondi/<int:id_domanda>', methods=['POST'])
@login_required
@conserva_form_se_errore('confirmAnswerModal{id_domanda}')
def rispondi_domanda(id_domanda):
    """Permette ai coordinatori di rispondere a una domanda."""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: Solo i coordinatori possono rispondere alle domande.", "danger")
        return redirect(url_for('dashboard'))

    domanda = domande_risposte_dao.get_domanda_by_id(id_domanda)
    if not domanda:
        flash("Errore: La domanda non esiste.", "danger")
        return redirect(url_for('dashboard'))

    # L'ID della proposta viene preso dal database e non dal form, così non può essere manipolato dall'utente
    id_proposta = domanda['id_proposta']

    # Solo il coordinatore proprietario della proposta può rispondere alle domande
    proposta = proposte_viaggio_dao.get_proposta_by_id(id_proposta)
    if not proposta or proposta['id_coordinatore'] != current_user.id:
        flash("Errore: Puoi rispondere solo alle domande sulle tue proposte.", "danger")
        return redirect(url_for('dashboard'))

    testo_risposta = request.form.get("testo_risposta")

    if not testo_risposta:
        flash("Errore: Il testo della risposta non può essere vuoto.", "danger")
        return redirect(url_for('proposta', id_proposta=id_proposta))

    # Il DAO restituisce una coppia (esito, messaggio): va separata, altrimenti la tupla risulta sempre "vera"
    success, message = domande_risposte_dao.rispondi_domanda(id_domanda, testo_risposta)

    if success:
        flash("Risposta inviata con successo!", "success")
    else:
        flash(message, "danger")

    return redirect(url_for('proposta', id_proposta=id_proposta))  # Reindirizza alla pagina della proposta con le domande



"""
Gestione delle foto profilo e foto proposte
"""


def allowed_file(filename):
    """Controlla se il file ha un'estensione valida."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()   # split sul punto con 1 come massimo di split, prende la seconda parte "[1]" e la rende minuscola
    return ext in ALLOWED_EXTENSIONS     # Controlla se l'estensione è in "ALLOWED EXTENSIONS"


def controlla_dimensioni(img):
    """Blocca le immagini con troppi pixel prima di decomprimerle (Image.open legge solo l'intestazione del file)."""
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError("Immagine troppo grande")


def process_profile_image(usr_image):
    """Ridimensiona, ritaglia e salva l'immagine profilo."""
    if usr_image and allowed_file(usr_image.filename):              # Se è stata caricata un'immagine e ha un'estensione valida 
        # Nome casuale generato dal server e salvato sempre come .jpg: non dipende dall'username, così un utente
        # non può sovrascrivere la foto di un altro (es. "caramel" vs "Caramel") o l'immagine di default
        filename = f"profilo_{secrets.token_hex(8)}.jpg"
        image_path = os.path.join(UPLOAD_FOLDER, PROFILE_FOLDER, filename)

        with Image.open(usr_image) as img:
            controlla_dimensioni(img)
            img = img.convert("RGB")  # Converte in RGB per salvare come JPG, nel caso in cui l'immagine sia PNG con sfondo trasparente potrebbe dare errori
            width, height = img.size  # Ottiene le dimensioni dell'immagine

            # Ridimensiona mantenendo il rapporto
            new_width = PROFILE_IMG_SIZE * width / height                               # Calcola la nuova larghezza mantenendo il rapporto
            img.thumbnail((new_width, PROFILE_IMG_SIZE), Image.Resampling.LANCZOS)      # Traforma l'immagine in una miniatura con dimensioni new_width x PROFILE_IMG_SIZE e utilizza l'algoritmo di ridimensionamento LANCZOS

            # Ritaglia l'immagine al centro per renderla quadrata
            left = (new_width / 2 - PROFILE_IMG_SIZE / 2)       # Punto di inizio del ritaglio
            right = (new_width / 2 + PROFILE_IMG_SIZE / 2)      # Punto di fine del ritaglio
            img = img.crop((left, 0, right, PROFILE_IMG_SIZE))  # Ritaglia l'immagine mantenendo l'altezza (0) e tagliando la larghezza

            # Salva come JPEG con compressione
            img.save(image_path, format="JPEG", quality=80)     # Salva l'immagine come JPEG con qualità 80

        return filename
    return None  # Nessuna immagine caricata


def process_trip_image(image, id_coordinatore):
    """Ridimensiona e salva l'immagine per la proposta con nome univoco."""
    if image and allowed_file(image.filename):
        timestamp = int(time.time())  # Otteniamo il timestamp attuale
        filename = secure_filename(f"trip_{timestamp}_{id_coordinatore}.jpg")  # Nome sicuro e univoco grazie al timestamp e usiamo id_coordinatore per facilitare successivamente l'inserimento del viaggio
        image_path = os.path.join(UPLOAD_FOLDER, TRIP_FOLDER, filename)

        with Image.open(image) as img:
            controlla_dimensioni(img)
            img = img.convert("RGB")  
            img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)  # Ridimensiona
            img.save(image_path, format="JPEG", quality=85)  # Salva l'immagine con compressione (qualità 85)

        return filename 
    return None  


""""
Gestione degli utenti e autenticazione
"""


@app.route('/register', methods=['POST'])
@conserva_form_se_errore('register', modale='authModal')
def register():
    """Gestisce la registrazione degli utenti."""
    user_data = request.form.to_dict()    # Ottiene i dati inviati dal form di registrazione

    # Controlli lato server: "required" e "maxlength" del form HTML si aggirano facilmente con una richiesta HTTP modificata
    if not user_data.get('username', '').strip() or len(user_data['username']) > 100:
        flash("Errore: L'username è obbligatorio e può avere al massimo 100 caratteri.", "danger")
        return redirect(url_for('home'))

    if not user_data.get('password') or len(user_data['password']) > 10000:
        flash("Errore: La password è obbligatoria e può avere al massimo 10000 caratteri.", "danger")
        return redirect(url_for('home'))

    if len(user_data.get('nome', '')) > 1000:
        flash("Errore: Il nome può avere al massimo 1000 caratteri.", "danger")
        return redirect(url_for('home'))

    if user_data.get('tipo_utente') not in ('0', '1'):     # 0 = Viaggiatore, 1 = Coordinatore
        flash("Errore: Tipo di utente non valido.", "danger")
        return redirect(url_for('home'))

    # Controlliamo se l'username esiste già
    if utenti_dao.get_user_by_username(user_data['username']):
        flash('Questo username è già in uso. Scegline un altro.', 'danger') 
        return redirect(url_for('home'))    # Se l'username esiste già, reindirizziamo l'utente alla home

    # Verifica che le password coincidano
    if user_data['password'] != user_data.get('password_confirm'):
        flash("Le password non coincidono, riprova.", "danger")
        return redirect(url_for('home'))
    
    # Convertiamo tipo_utente a intero
    user_data['tipo_utente'] = int(user_data['tipo_utente'])
        
    # Se è un coordinatore, il nome deve essere obbligatorio
    if user_data['tipo_utente'] == 1 and not user_data.get('nome'):         # Gestiamo il caso in cui l'utente è un coordinatore e non ha inserito il nome
        flash('Il campo "nome" è obbligatorio per i coordinatori.', 'danger')
        return redirect(url_for('home'))
    
    # Hash della password
    user_data['password'] = generate_password_hash(user_data['password'])

    # Gestione immagine profilo
    usr_image = request.files.get('immagine_profilo')  # Uso .get() per evitare errori perché se l'utente non carica un'immagine, il valore sarà None

    #Aggiungiamo un controllo in caso l'utente invii una richiesta HTTP personalizzata bypassando la restrizione nel frontend
    if usr_image and usr_image.filename != "":  # Verifica se l'utente ha caricato un file
        if not allowed_file(usr_image.filename):  # Controlla se l'estensione è valida
            flash("Formato immagine non supportato. Usa solo PNG, JPG o JPEG.", "danger")
            return redirect(url_for('home'))
        try:
            user_data['immagine_profilo'] = process_profile_image(usr_image)
        except ERRORI_IMMAGINE:
            flash("Errore: Immagine non valida o troppo grande.", "danger")
            return redirect(url_for('home'))
    else:
        user_data['immagine_profilo'] = "default_pro_pic.jpg"  # Assegniamo l'immagine predefinita se l'utente non ha caricato un'immagine

    # Aggiungiamo l'utente al database
    success = utenti_dao.add_user(user_data)

    if success:
        flash('Registrazione completata! Ora puoi accedere.', 'success')
        return redirect(url_for('home'))    # Se la registrazione è andata a buon fine, reindirizziamo l'utente alla pagina home
    else:
        return redirect(url_for('home'))


@app.route('/login', methods=['POST'])
@conserva_form_se_errore('login', modale='authModal')
def login():
    """Gestisce il login degli utenti."""
    user_data = request.form.to_dict()

    # Recuperiamo l'utente dal database
    db_user = utenti_dao.get_user_by_username(user_data.get('username', ''))    # .get() evita un errore 500 se il campo manca

    # Verifica credenziali
    if not db_user or not check_password_hash(db_user['password'], user_data.get('password', '')):  # Gestiamo il caso in cui l'utente non esiste o se coppia "utente-password" non corrisponde
        flash('Credenziali non valide, riprova', 'danger')
        return redirect(url_for('home'))   

    # Creiamo un oggetto User e autentichiamo l'utente
    user = User(
        id=db_user['id'],
        username=db_user['username'],
        password=db_user['password'],
        tipo_utente=db_user['tipo_utente'],
        nome=db_user['nome'],
        immagine_profilo=db_user['immagine_profilo']
    )

    login_user(user, remember=True)    # Autentica l'utente e crea una cookie di sessione
    flash(f'Login effettuato con successo!', 'success')

    return redirect(url_for('dashboard'))


@app.route("/logout", methods=['POST'])     # Solo POST: così il logout è protetto dal token CSRF e un sito esterno non può forzarlo con un semplice link
@login_required   # Solo utenti autenticati possono eseguire il logout
def logout():
    """Gestisce il logout degli utenti."""
    logout_user()
    flash("Hai effettuato il logout con successo", "info")
    return redirect(url_for('home'))


@login_manager.user_loader
def load_user(user_id):
    """Carica un utente dal database per Flask-Login."""
    db_user = utenti_dao.get_user_by_id(user_id)        # Ottiene un utente dal database
    return User(
    id=db_user['id'],
    username=db_user['username'],
    password=db_user['password'],
    tipo_utente=db_user['tipo_utente'],
    nome=db_user['nome'],
    immagine_profilo=db_user['immagine_profilo']
) if db_user else None                                  # Restituisce un oggetto User se l'utente esiste, altrimenti None

