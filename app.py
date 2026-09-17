"""
app.py - Configura Flask, Flask-Login e gestisce l'autenticazione utenti.
Include le funzioni per la gestione delle pagine del sito, delle proposte di viaggio, delle prenotazioni, delle domande-risposte e delle immagini.
"""

from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename   # Per evitare attacchi nel caso in cui il nome del file contenga caratteri speciali che potrebbero essere interpretati come path dal sistema operativo
import datetime, time, os, secrets

from PIL import Image   # Pillow - Python Imaging Library used to pre-process images before saving them to the server

import utenti_dao, proposte_viaggio_dao, prenotazioni_dao, domande_risposte_dao
from models import User

UPLOAD_FOLDER = "static/uploads/"
PROFILE_FOLDER = "profili/"         # Sottocartella per le immagini profilo
TRIP_FOLDER = "proposte/"  # Sottocartella per le immagini delle proposte
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
PROFILE_IMG_SIZE = 100  # Thumbnail 100x100 px
MAX_WIDTH = 800  # Massima larghezza immagine proposta
MAX_HEIGHT = 600 # Massima altezza immagine proposta


app = Flask(__name__)
# La chiave segreta firma i cookie di sessione: va letta da variabile d'ambiente e non scritta nel codice
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    # Fallback solo per lo sviluppo locale: chiave casuale diversa a ogni avvio (le sessioni non sopravvivono al riavvio)
    app.secret_key = secrets.token_hex(32)
    print("ATTENZIONE: SECRET_KEY non impostata, uso una chiave temporanea valida solo per lo sviluppo locale.")

# Configurazione Flask-Login
login_manager = LoginManager()       # Crea un oggetto di tipo LoginManager
login_manager.init_app(app)          # Inizializza l'applicazione Flask
login_manager.login_view = "home"   # Se un utente non autenticato prova ad accedere a una pagina protetta, viene reindirizzato alla pagina "/home"

 
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

    # Se l'utente è un viaggiatore, otteniamo il numero di posti disponibili
    posti_disponibili = prenotazioni_dao.get_posti_disponibili(id_proposta) if current_user.tipo_utente == 0 else None

    # Se l'utente è un coordinatore, otteniamo l'elenco dei partecipanti
    partecipanti = prenotazioni_dao.get_partecipanti_by_proposta(id_proposta) if current_user.tipo_utente == 1 else []

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

    return render_template('proposta.html', proposta=proposta, partecipanti=partecipanti, domande=domande, posti_disponibili=posti_disponibili, prenotato=prenotato)


"""
Gestione delle proposte di viaggio
"""


@app.route('/proposte_bozze', methods=['GET'])
@login_required
def lista_bozze():
    """Mostra solo le proposte in bozza del coordinatore loggato."""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: questa sezione è riservata ai coordinatori.", "danger")
        return redirect(url_for('home'))

    bozze = proposte_viaggio_dao.get_bozze_by_coordinatore(current_user.id)
    return redirect(url_for('dashboard'), bozze=bozze)  


@app.route('/proposte_pubblicate', methods=['GET'])
@login_required
def lista_pubblicate():
    """Mostra solo le proposte pubblicate del coordinatore loggato."""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: questa sezione è riservata ai coordinatori.", "danger")
        return redirect(url_for('home'))

    pubblicate = proposte_viaggio_dao.get_pubblicate_by_coordinatore(current_user.id)
    return redirect(url_for('dashboard'), pubblicate=pubblicate)  


@app.route('/proposte_pubblicate_all', methods=['GET'])  
@login_required
def lista_proposte_pubblicate():
    """Mostra tutte le proposte pubblicate per i viaggiatori."""
    if current_user.tipo_utente != 0:
        flash("Accesso negato: questa sezione è riservata ai viaggiatori.", "danger")
        return redirect(url_for('home'))
    proposte = proposte_viaggio_dao.get_proposte_pubblicate()
    prenotazioni = prenotazioni_dao.get_prenotazioni_by_viaggiatore(current_user.id)    # Passiamo anche le prenotazioni

    return redirect(url_for('dashboard'), proposte=proposte, prenotazioni=prenotazioni)



@app.route('/nuova_proposta', methods=['POST'])
@login_required
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
    dati_proposta['budget_trasporto'] = round(float(dati_proposta['budget_trasporto']), 2) if dati_proposta.get('budget_trasporto') else None   # "round" arrotonda il valore a 2 decimali
    dati_proposta['budget_alloggio'] = round(float(dati_proposta['budget_alloggio']), 2) if dati_proposta.get('budget_alloggio') else None
    dati_proposta['budget_attivita'] = round(float(dati_proposta['budget_attivita']), 2) if dati_proposta.get('budget_attivita') else None


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
        immagine = process_trip_image(trip_image, dati_proposta['id_coordinatore'])
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
    
    # Gestione immagine proposta
    dati_proposta = request.form.to_dict()
    nuova_immagine = request.files.get('immagine_proposta')  # Prendiamo direttamente il file

    # Se non viene caricata una nuova immagine, passiamo None
    immagine = None
    if nuova_immagine and nuova_immagine.filename.strip():  
        if not allowed_file(nuova_immagine.filename):  
            flash("Formato immagine non supportato. Usa solo PNG, JPG o JPEG.", "danger")
            return redirect(url_for('dashboard'))
        immagine = process_trip_image(nuova_immagine, proposta['id_coordinatore'])


    # Controllo sulla lunghezza della descrizione
    if len(dati_proposta['descrizione']) > 1000:
        flash("Errore: La descrizione non può superare i 1000 caratteri.", "danger")
        return redirect(url_for('dashboard'))
        

    # Controllo che i campi essenziali non siano vuoti
    campi_obbligatori = ["destinazione", "data_inizio", "data_fine", "descrizione", "num_massimo"]
    for campo in campi_obbligatori:
        if not dati_proposta.get(campo):
            flash(f"Errore: il campo '{campo}' è obbligatorio.", "danger")
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
    # Conversione dei campi numerici opzionali
    dati_proposta['budget_trasporto'] = round(float(dati_proposta['budget_trasporto']), 2) if dati_proposta.get('budget_trasporto') else None
    dati_proposta['budget_alloggio'] = round(float(dati_proposta['budget_alloggio']), 2) if dati_proposta.get('budget_alloggio') else None
    dati_proposta['budget_attivita'] = round(float(dati_proposta['budget_attivita']), 2) if dati_proposta.get('budget_attivita') else None

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
def aggiungi_domanda(id_proposta):
    """Permette ai viaggiatori di fare una domanda su una proposta."""
    if current_user.tipo_utente != 0:
        flash("Accesso negato: Solo i viaggiatori possono fare domande.", "danger")
        return redirect(url_for('dashboard'))

    testo_domanda = request.form.get("testo_domanda")
    
    if not testo_domanda:
        flash("Errore: Il testo della domanda non può essere vuoto.", "danger")
        return redirect(url_for('proposta', id_proposta=id_proposta)) 

    success = domande_risposte_dao.add_domanda(current_user.id, id_proposta, testo_domanda)

    if success:
        flash("Domanda inviata con successo!", "success")
    else:
        flash("Errore nell'invio della domanda.", "danger")

    return redirect(url_for('proposta', id_proposta=id_proposta))



@app.route('/domande_rispondi/<int:id_domanda>', methods=['POST'])
@login_required
def rispondi_domanda(id_domanda):
    """Permette ai coordinatori di rispondere a una domanda."""
    if current_user.tipo_utente != 1:
        flash("Accesso negato: Solo i coordinatori possono rispondere alle domande.", "danger")
        return redirect(url_for('dashboard'))

    testo_risposta = request.form.get("testo_risposta")
    id_proposta = request.form.get("id_proposta")  # Ottieni l'ID della proposta dalla form


    if not testo_risposta:
        flash("Errore: Il testo della risposta non può essere vuoto.", "danger")
        return redirect(url_for('proposta', id_proposta=id_proposta))
    
    # Se id_proposta è None, mostra un errore
    if not id_proposta:
        flash("Errore interno: ID proposta non ricevuto.", "danger")
        return redirect(url_for('dashboard'))    # Evitiamo errori se id_proposta non è disponibile (quello inviato con l'input hidden)

    success = domande_risposte_dao.rispondi_domanda(id_domanda, testo_risposta)

    if success:
        flash("Risposta inviata con successo!", "success")
    else:
        flash("Errore nell'invio della risposta.", "danger")

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


def process_profile_image(usr_image, username):
    """Ridimensiona, ritaglia e salva l'immagine profilo."""
    if usr_image and allowed_file(usr_image.filename):              # Se è stata caricata un'immagine e ha un'estensione valida 
        filename = secure_filename(username.lower() + ".jpg")       # Salvato sempre come .jpg e usa secure_filename per evitare attacchi su file system di un server vulnerabile con attacchi di path traversal
        image_path = f"{UPLOAD_FOLDER}{PROFILE_FOLDER}{filename}"  

        with Image.open(usr_image) as img:
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
        image_path = f"{UPLOAD_FOLDER}{TRIP_FOLDER}{filename}"

        with Image.open(image) as img:
            img = img.convert("RGB")  
            img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)  # Ridimensiona
            img.save(image_path, format="JPEG", quality=85)  # Salva l'immagine con compressione (qualità 85)

        return filename 
    return None  


""""
Gestione degli utenti e autenticazione
"""


@app.route('/register', methods=['POST'])
def register():
    """Gestisce la registrazione degli utenti."""
    user_data = request.form.to_dict()    # Ottiene i dati inviati dal form di registrazione

    # Controlliamo se l'username esiste già
    if utenti_dao.get_user_by_username(user_data['username']):
        flash('Questo username è già in uso. Scegline un altro.', 'danger') 
        return redirect(url_for('home'))    # Se l'username esiste già, reindirizziamo l'utente alla home

    # Verifica che le password coincidano
    if user_data['password'] != user_data['password_confirm']:
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
        user_data['immagine_profilo'] = process_profile_image(usr_image, user_data['username'])
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
def login():
    """Gestisce il login degli utenti."""
    user_data = request.form.to_dict()

    # Recuperiamo l'utente dal database
    db_user = utenti_dao.get_user_by_username(user_data['username'])

    # Verifica credenziali
    if not db_user or not check_password_hash(db_user['password'], user_data['password']):  # Gestiamo il caso in cui l'utente non esiste o se coppia "utente-password" non corrisponde
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


@app.route("/logout")
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

