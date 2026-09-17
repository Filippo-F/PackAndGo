"""
models.py - Definisce la classe User per l'autenticazione con Flask-Login.
"""

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, password, tipo_utente, nome=None, immagine_profilo=None):   # "self" rappresenta l'istanza della classe, ovvero l'oggetto creato con la classe User
        self.id = id     
        self.username = username
        self.password = password
        self.tipo_utente = tipo_utente
        self.nome = nome
        self.immagine_profilo = immagine_profilo
