#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDAV Explorer - Dialogue de connexion
"""

from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *

import requests
from requests.auth import HTTPBasicAuth

class WebDAVConnectionDialog(QDialog):
    """Boîte de dialogue pour configurer les connexions WebDAV"""
    
    def __init__(self, parent=None, connection_info=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration WebDAV")
        self.setModal(True)
        self.resize(500, 400)
        
        # Données existantes pour modification
        self.connection_info = connection_info or {}
        
        self.setup_ui()
        self.load_connection_info()
    
    def setup_ui(self):
        """Construction de l'interface"""
        layout = QVBoxLayout(self)
        
        # === INFORMATIONS GÉNÉRALES ===
        general_group = QGroupBox("Informations générales")
        general_layout = QFormLayout(general_group)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex: CRAIG PCRS")
        general_layout.addRow("Nom de la connexion:", self.name_edit)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://drive.opendata.craig.fr/s/opendata")
        general_layout.addRow("URL du serveur:", self.url_edit)
        
        layout.addWidget(general_group)
        
        # === AUTHENTIFICATION ===
        auth_group = QGroupBox("Authentification")
        auth_layout = QFormLayout(auth_group)
        
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("opendata")
        auth_layout.addRow("Nom d'utilisateur:", self.username_edit)
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Laisser vide si aucun mot de passe")
        auth_layout.addRow("Mot de passe:", self.password_edit)
        
        layout.addWidget(auth_group)
        
        # === OPTIONS AVANCÉES ===
        advanced_group = QGroupBox("Options avancées")
        advanced_layout = QFormLayout(advanced_group)
        
        self.root_path_edit = QLineEdit()
        self.root_path_edit.setText("/")
        self.root_path_edit.setPlaceholderText("/ortho/PCRS_5cm")
        advanced_layout.addRow("Chemin racine:", self.root_path_edit)
        
        layout.addWidget(advanced_group)
        
        # === EXEMPLES DE CONFIGURATION ===
        examples_group = QGroupBox("Exemples de configuration")
        examples_layout = QVBoxLayout(examples_group)
        
        examples_text = QTextEdit()
        examples_text.setMaximumHeight(120)
        examples_text.setReadOnly(True)
        examples_text.setHtml("""
<b>CRAIG PCRS:</b><br>
• URL: https://drive.opendata.craig.fr/s/opendata<br>
• Utilisateur: opendata<br>
• Mot de passe: (vide)<br>
• Chemin racine: /ortho/PCRS_5cm<br><br>

<b>Nextcloud personnel:</b><br>
• URL: https://moncloud.example.com/remote.php/dav/files/username<br>
• Utilisateur: votre_nom<br>
• Mot de passe: votre_mot_de_passe<br>
• Chemin racine: /GIS
        """)
        examples_layout.addWidget(examples_text)
        
        layout.addWidget(examples_group)
        
        # === BOUTONS ===
        buttons_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("🧪 Tester la connexion")
        self.test_btn.clicked.connect(self.test_connection)
        buttons_layout.addWidget(self.test_btn)
        
        buttons_layout.addStretch()
        
        self.ok_btn = QPushButton("✅ OK")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("❌ Annuler")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(buttons_layout)
    
    def load_connection_info(self):
        """Charge les informations de connexion existante"""
        if self.connection_info:
            self.name_edit.setText(self.connection_info.get('name', ''))
            self.url_edit.setText(self.connection_info.get('url', ''))
            self.username_edit.setText(self.connection_info.get('username', ''))
            self.password_edit.setText(self.connection_info.get('password', ''))
            self.root_path_edit.setText(self.connection_info.get('root_path', '/'))
    
    def get_connection_info(self):
        """Retourne les informations de connexion"""
        return {
            'name': self.name_edit.text().strip(),
            'url': self.url_edit.text().strip().rstrip('/'),
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text(),
            'root_path': self.root_path_edit.text().strip() or '/'
        }
    
    def test_connection(self):
        """Teste la connexion WebDAV"""
        conn_info = self.get_connection_info()
        
        if not conn_info['name'] or not conn_info['url']:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir au moins un nom et une URL")
            return
        
        # Désactiver le bouton pendant le test
        self.test_btn.setEnabled(False)
        self.test_btn.setText("🔄 Test en cours...")
        
        try:
            session = requests.Session()
            
            if conn_info['username']:
                session.auth = HTTPBasicAuth(conn_info['username'], conn_info['password'])
            
            session.headers.update({
                'User-Agent': 'QGIS-WebDAV-Explorer-Test/1.0'
            })
            
            # Test de connexion
            test_url = conn_info['url']
            response = session.request('PROPFIND', test_url, 
                                     headers={'Depth': '0'}, 
                                     timeout=10)
            
            if response.status_code in [200, 207]:
                QMessageBox.information(self, "Succès", "✅ Connexion réussie !")
            elif response.status_code == 401:
                QMessageBox.warning(self, "Authentification", 
                                  "❌ Erreur d'authentification.\nVérifiez vos identifiants.")
            elif response.status_code == 404:
                QMessageBox.warning(self, "Non trouvé", 
                                  "❌ URL non trouvée.\nVérifiez l'adresse du serveur.")
            else:
                QMessageBox.warning(self, "Erreur", 
                                  f"❌ Erreur HTTP {response.status_code}")
            
        except requests.exceptions.ConnectionError:
            QMessageBox.critical(self, "Erreur de connexion", 
                               "❌ Impossible de se connecter au serveur.\nVérifiez l'URL et votre connexion internet.")
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "Timeout", 
                              "❌ Timeout de connexion.\nLe serveur met trop de temps à répondre.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"❌ Erreur inattendue:\n{str(e)}")
        
        finally:
            # Réactiver le bouton
            self.test_btn.setEnabled(True)
            self.test_btn.setText("🧪 Tester la connexion")
    
    def accept(self):
        """Valide et ferme la boîte de dialogue"""
        conn_info = self.get_connection_info()
        
        if not conn_info['name'].strip():
            QMessageBox.warning(self, "Erreur", "Veuillez saisir un nom pour la connexion")
            self.name_edit.setFocus()
            return
        
        if not conn_info['url'].strip():
            QMessageBox.warning(self, "Erreur", "Veuillez saisir l'URL du serveur")
            self.url_edit.setFocus()
            return
        
        super().accept()