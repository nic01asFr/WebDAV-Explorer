#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDAV Generic Explorer - Explorateur WebDAV générique intelligent
Détection automatique des types de fichiers et traitement adapté
"""

from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *

import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, quote, unquote
import tempfile
import json
import zipfile
from pathlib import Path as PyPath
import re
import os
import shutil
import sqlite3
import time
import urllib.parse

class WebDAVDockWidget(QDockWidget):
    """Explorateur WebDAV générique avec détection intelligente des formats"""
    
    def __init__(self, iface, parent=None):
        super().__init__("WebDAV Generic Explorer", parent)
        self.iface = iface
        self.setObjectName("WebDAVGenericExplorer")
        
        # Configuration
        self.connections = {}
        self.current_connection = None
        self.session = None
        self.current_path = "/"
        self.current_mode = "webdav"  # "webdav" ou "geopackage"
        self.current_geopackage = None
        
        # Détecteurs de types de fichiers
        self.file_handlers = {
            # Rasters
            '.tif': {'type': 'raster', 'icon': 'raster', 'handler': self.handle_raster_file},
            '.tiff': {'type': 'raster', 'icon': 'raster', 'handler': self.handle_raster_file},
            '.ecw': {'type': 'raster', 'icon': 'raster', 'handler': self.handle_raster_file},
            '.jp2': {'type': 'raster', 'icon': 'raster', 'handler': self.handle_raster_file},
            
            # Vecteurs
            '.shp': {'type': 'vector', 'icon': 'vector', 'handler': self.handle_vector_file},
            '.gpkg': {'type': 'geopackage', 'icon': 'database', 'handler': self.handle_geopackage_file},
            '.sqlite': {'type': 'database', 'icon': 'database', 'handler': self.handle_database_file},
            '.geojson': {'type': 'vector', 'icon': 'vector', 'handler': self.handle_vector_file},
            '.kml': {'type': 'vector', 'icon': 'vector', 'handler': self.handle_vector_file},
            
            # Archives
            '.zip': {'type': 'archive', 'icon': 'archive', 'handler': self.handle_archive_file},
            '.tar': {'type': 'archive', 'icon': 'archive', 'handler': self.handle_archive_file},
            '.gz': {'type': 'archive', 'icon': 'archive', 'handler': self.handle_archive_file},
            
            # Projets
            '.qgs': {'type': 'qgis_project', 'icon': 'project', 'handler': self.handle_qgis_project},
            '.qgz': {'type': 'qgis_project', 'icon': 'project', 'handler': self.handle_qgis_project},
            
            # Métadonnées et config
            '.xml': {'type': 'metadata', 'icon': 'text', 'handler': self.handle_metadata_file},
            '.json': {'type': 'metadata', 'icon': 'text', 'handler': self.handle_metadata_file},
            
            # Types spéciaux pour modes particuliers
            '.html': {'type': 'html_debug', 'icon': 'text', 'handler': self.handle_generic_file},
        }
        
        self.setup_ui()
        self.load_connections()
    
    def setup_ui(self):
        """Interface utilisateur générique et flexible"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # === HEADER ===
        header_group = QGroupBox("🌐 WebDAV Generic Explorer")
        header_layout = QVBoxLayout(header_group)
        
        # Connexion
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Connexion:"))
        
        self.connection_combo = QComboBox()
        self.connection_combo.currentTextChanged.connect(self.on_connection_changed)
        conn_layout.addWidget(self.connection_combo)
        
        self.new_conn_btn = QPushButton("➕")
        self.new_conn_btn.setToolTip("Nouvelle connexion")
        self.new_conn_btn.clicked.connect(self.show_connection_dialog)
        conn_layout.addWidget(self.new_conn_btn)
        
        self.connect_btn = QPushButton("🔌 Connecter")
        self.connect_btn.clicked.connect(self.smart_connect)
        conn_layout.addWidget(self.connect_btn)
        
        header_layout.addLayout(conn_layout)
        
        # Status
        self.connection_status = QLabel("❌ Non connecté")
        header_layout.addWidget(self.connection_status)
        
        layout.addWidget(header_group)
        
        # === NAVIGATION ===
        nav_group = QGroupBox("🗂️ Navigation")
        nav_layout = QVBoxLayout(nav_group)
        
        # Barre de navigation
        nav_bar = QHBoxLayout()
        
        self.back_btn = QPushButton("⬅️")
        self.back_btn.setToolTip("Retour")
        self.back_btn.clicked.connect(self.navigate_back)
        self.back_btn.setEnabled(False)
        nav_bar.addWidget(self.back_btn)
        
        self.up_btn = QPushButton("⬆️")
        self.up_btn.setToolTip("Dossier parent")
        self.up_btn.clicked.connect(self.navigate_up)
        self.up_btn.setEnabled(False)
        nav_bar.addWidget(self.up_btn)
        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setToolTip("Actualiser")
        self.refresh_btn.clicked.connect(self.refresh_current_location)
        self.refresh_btn.setEnabled(False)
        nav_bar.addWidget(self.refresh_btn)
        
        # Mode d'affichage
        nav_bar.addWidget(QLabel("|"))
        self.mode_label = QLabel("📁 WebDAV")
        nav_bar.addWidget(self.mode_label)
        
        nav_bar.addStretch()
        nav_layout.addLayout(nav_bar)
        
        # Chemin avec breadcrumb
        self.path_label = QLabel("📍 Chemin: /")
        self.path_label.setStyleSheet("font-family: monospace; background: #f0f0f0; padding: 3px;")
        nav_layout.addWidget(self.path_label)
        
        layout.addWidget(nav_group)
        
        # === EXPLORATEUR ===
        explorer_group = QGroupBox("📋 Contenu")
        explorer_layout = QVBoxLayout(explorer_group)
        
        # Filtres
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Afficher:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "Tous les éléments",
            "Dossiers seulement", 
            "Fichiers géographiques",
            "Archives et bases",
            "Images raster",
            "Données vecteur",
            "Projets QGIS"
        ])
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_combo)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Rechercher...")
        self.search_edit.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_edit)
        
        explorer_layout.addLayout(filter_layout)
        
        # Table de contenu avec colonnes adaptatives
        self.content_table = QTableWidget()
        self.content_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.content_table.setAlternatingRowColors(True)
        self.content_table.setSortingEnabled(True)
        self.content_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.content_table.customContextMenuRequested.connect(self.show_context_menu)
        self.content_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.content_table.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        # Headers initiaux (seront adaptés selon le contenu)
        self.content_table.setColumnCount(6)
        self.content_table.setHorizontalHeaderLabels([
            "Nom", "Type", "Taille", "Date", "Description", "Action"
        ])
        
        explorer_layout.addWidget(self.content_table)
        
        # Stats
        self.stats_label = QLabel("📊 Éléments: 0")
        explorer_layout.addWidget(self.stats_label)
        
        layout.addWidget(explorer_group)
        
        # === PREVIEW ===
        preview_group = QGroupBox("👁️ Aperçu")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_text = QTextEdit()
        self.preview_text.setMaximumHeight(120)
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Sélectionnez un élément pour voir ses détails...")
        preview_layout.addWidget(self.preview_text)
        
        layout.addWidget(preview_group)
        
        # === ACTIONS ===
        actions_group = QGroupBox("⚡ Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        # Actions principales
        main_actions = QHBoxLayout()
        
        self.open_btn = QPushButton("📂 Ouvrir/Explorer")
        self.open_btn.clicked.connect(self.open_selected)
        self.open_btn.setEnabled(False)
        main_actions.addWidget(self.open_btn)
        
        self.load_btn = QPushButton("📥 Charger dans QGIS")
        self.load_btn.clicked.connect(self.load_selected)
        self.load_btn.setEnabled(False)
        main_actions.addWidget(self.load_btn)
        
        self.download_btn = QPushButton("💾 Télécharger")
        self.download_btn.clicked.connect(self.download_selected)
        self.download_btn.setEnabled(False)
        main_actions.addWidget(self.download_btn)
        
        actions_layout.addLayout(main_actions)
        
        # Actions d'enregistrement
        save_actions = QHBoxLayout()
        
        self.save_layer_btn = QPushButton("💾 Enregistrer couche active")
        self.save_layer_btn.clicked.connect(self.save_current_layer_to_webdav)
        self.save_layer_btn.setToolTip("Enregistrer la couche active sur le WebDAV")
        save_actions.addWidget(self.save_layer_btn)
        
        self.save_project_btn = QPushButton("📋 Enregistrer projet QGIS")
        self.save_project_btn.clicked.connect(self.save_current_project_to_webdav)
        self.save_project_btn.setToolTip("Enregistrer le projet QGIS actuel sur le WebDAV")
        save_actions.addWidget(self.save_project_btn)
        
        actions_layout.addLayout(save_actions)
        
        # Actions spécialisées (apparaissent selon le contexte)
        self.specialized_actions = QHBoxLayout()
        actions_layout.addLayout(self.specialized_actions)
        
        # Options
        options_layout = QHBoxLayout()
        
        self.auto_preview_check = QCheckBox("Aperçu automatique")
        self.auto_preview_check.setChecked(True)
        options_layout.addWidget(self.auto_preview_check)
        
        self.create_groups_check = QCheckBox("Grouper par source")
        self.create_groups_check.setChecked(True)
        options_layout.addWidget(self.create_groups_check)
        
        actions_layout.addLayout(options_layout)
        
        layout.addWidget(actions_group)
        
        # === STATUS ===
        self.status_label = QLabel("Prêt à explorer")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.setWidget(widget)
    
    def smart_connect(self):
        """Connexion intelligente avec détection automatique du protocole"""
        if not self.current_connection:
            QMessageBox.warning(self, "Erreur", "Sélectionnez une connexion")
            return
        
        self.status_label.setText("🔍 Détection du protocole...")
        
        try:
            # Normaliser l'URL de connexion pour éviter les problèmes de chemins
            base_url = self.current_connection['url'].strip()
            
            # S'assurer que l'URL commence par un protocole
            if not base_url.startswith('http'):
                base_url = 'https://' + base_url.lstrip('/')
                self.status_label.setText(f"🔄 Ajout du protocole HTTPS à l'URL: {base_url}")
                
            # S'assurer que le format du protocole est correct
            if base_url.startswith('http:/') and not base_url.startswith('http://'):
                base_url = base_url.replace('http:/', 'http://')
                self.status_label.setText(f"🔄 Correction du format HTTP: {base_url}")
                
            if base_url.startswith('https:/') and not base_url.startswith('https://'):
                base_url = base_url.replace('https:/', 'https://')
                self.status_label.setText(f"🔄 Correction du format HTTPS: {base_url}")
            
            # Enlever les slashes finaux
            base_url = base_url.rstrip('/')
            
            # Cas spécial pour CRAIG : vérifier le format de l'URL
            if 'craig.fr' in base_url and '/s/' in base_url:
                # Reconstruire l'URL pour s'assurer qu'elle est bien formée
                url_parts = base_url.split('//')
                if len(url_parts) > 1:
                    protocol = url_parts[0] + '//'
                    domain_and_path = url_parts[1]
                    
                    # Corriger les double slashes dans la partie après le protocole
                    while '//' in domain_and_path:
                        domain_and_path = domain_and_path.replace('//', '/')
                    
                    base_url = protocol + domain_and_path
                    self.status_label.setText(f"🔄 URL CRAIG reconstruite: {base_url}")
            
            self.current_connection['url'] = base_url
            
            # Détecter si c'est un serveur Nextcloud ou similaire
            is_nextcloud = any(indicator in base_url.lower() for indicator in 
                            ['/remote.php/dav/', '/index.php/dav/', '/owncloud/remote.php/'])
            
            # Détecter si c'est potentiellement un serveur CRAIG ou un partage Nextcloud
            is_craig = 'craig.fr' in base_url.lower()
            is_shared_link = '/s/' in base_url.lower() or '/index.php/s/' in base_url.lower()
                
            # Créer session
            self.session = requests.Session()
            
            if self.current_connection.get('username'):
                self.session.auth = HTTPBasicAuth(
                    self.current_connection['username'],
                    self.current_connection['password']
                )
            
            self.session.headers.update({
                'User-Agent': 'QGIS-WebDAV-Generic-Explorer/1.0'
            })
            
            # Tester différentes approches
            # 1. Test WebDAV PROPFIND
            try:
                # Pour Nextcloud et CRAIG, utiliser directement l'URL fournie sans modification
                test_url = base_url
                
                self.status_label.setText(f"🔍 Test WebDAV sur {test_url}...")
                response = self.session.request('PROPFIND', test_url, 
                                              headers={'Depth': '0'}, 
                                              timeout=10)
                
                if response.status_code in [200, 207]:
                    if is_nextcloud:
                        self.connection_status.setText("✅ Connecté (NextCloud/WebDAV)")
                    elif is_craig:
                        self.connection_status.setText("✅ Connecté (CRAIG/WebDAV)")
                    else:
                        self.connection_status.setText("✅ Connecté (WebDAV)")
                    self.current_mode = "webdav"
                    self.finalize_connection()
                    return
            except Exception as e:
                self.status_label.setText(f"❓ Test WebDAV échoué: {str(e)}")
            
            # 2. Test pour lien partagé Nextcloud (comme celui du CRAIG)
            if is_shared_link:
                try:
                    self.status_label.setText(f"🔍 Test de lien partagé sur {base_url}...")
                    
                    # Pour les liens partagés, on utilise d'abord une requête GET
                    response = self.session.get(base_url, timeout=10)
                    
                    if response.status_code == 200:
                        # C'est un partage accessible, maintenant on cherche l'URL WebDAV
                        self.status_label.setText("✅ Lien de partage Nextcloud détecté")
                        
                        # Adapter l'URL pour le WebDAV du lien partagé
                        # Format typique: de "/s/token" vers "/public.php/webdav"
                        if '/s/' in base_url:
                            share_info = self.get_nextcloud_share_info()
                            if share_info:
                                self.current_connection['webdav_url'] = share_info['public_webdav']
                                self.status_label.setText(f"🔄 Utilisation de l'URL WebDAV: {self.current_connection['webdav_url']}")
                                
                                # Stocker les informations du partage pour utilisation ultérieure
                                self.current_connection['share_info'] = share_info
                        
                        # Configuration pour des serveurs spécifiques
                        # Configurer l'authentification pour les liens partagés
                        self.configure_shared_link_auth()
                        
                        # Afficher un message personnalisé pour CRAIG
                        if 'craig.fr/s/opendata' in base_url.lower():
                            self.connection_status.setText("✅ Connecté (CRAIG OpenData)")
                            
                        self.current_mode = "nextcloud_share"
                        self.finalize_connection()
                        return
                        
                except Exception as e:
                    self.status_label.setText(f"❓ Test lien partagé échoué: {str(e)}")
                    
            # 3. Test HTTP GET (pour partages publics standard)
            try:
                response = self.session.get(base_url, timeout=10)
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    
                    # Si c'est le serveur CRAIG, utiliser le mode WebDAV même sur HTTP
                    if is_craig:
                        self.connection_status.setText("✅ Connecté (CRAIG/WebDAV sur HTTP)")
                        self.current_mode = "webdav"  # Utiliser WebDAV même si la connexion est HTTP
                        self.finalize_connection()
                        return
                    elif 'html' in content_type:
                        self.connection_status.setText("✅ Connecté (HTTP/HTML)")
                        self.current_mode = "http_html"
                        self.finalize_connection()
                        return
                    else:
                        self.connection_status.setText("✅ Connecté (HTTP)")
                        self.current_mode = "http_direct"
                        self.finalize_connection()
                        return
            except Exception as e:
                self.status_label.setText(f"❓ Test HTTP échoué: {str(e)}")
            
            # 3. Dernière tentative spécifique pour le CRAIG (méthode hybride)
            if is_craig:
                try:
                    # Utiliser le mode WebDAV mais avec une approche HTTP
                    self.connection_status.setText("✅ Connecté (CRAIG/Hybride)")
                    self.current_mode = "webdav_craig"
                    self.finalize_connection()
                    return
                except Exception as e:
                    self.status_label.setText(f"❓ Tentative CRAIG hybride échouée: {str(e)}")
            
            # 4. Échec de toutes les méthodes
            raise Exception("Aucun protocole supporté détecté")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur de connexion", 
                               f"Impossible de se connecter:\n{str(e)}")
            self.status_label.setText("❌ Échec de connexion")
    
    def finalize_connection(self):
        """Finalise la connexion et active l'interface"""
        # Configuration spéciale pour les liens partagés
        if self.is_nextcloud_shared_link():
            self.configure_shared_link_auth()
        
        # Activer les contrôles
        self.up_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        
        # Activer les boutons d'enregistrement
        self.save_layer_btn.setEnabled(True)
        self.save_project_btn.setEnabled(True)
        
        # Correction pour les URLs Nextcloud et similaires
        # Éviter de dupliquer les chemins dans l'URL
        if self.current_mode == "webdav":
            # Si l'URL contient déjà un chemin WebDAV complet, utiliser seulement '/' comme chemin racine
            base_url = self.current_connection['url'].lower()
            webdav_path_indicators = ['/remote.php/dav/', '/index.php/dav/', '/owncloud/remote.php/']
            
            if any(indicator in base_url for indicator in webdav_path_indicators):
                self.status_label.setText("ℹ️ Détection de serveur Nextcloud/ownCloud")
                self.current_path = '/'
            else:
                # Utiliser le chemin racine défini dans la configuration
                self.current_path = self.current_connection.get('root_path', '/')
                if not self.current_path.startswith('/'):
                    self.current_path = '/' + self.current_path
        else:
            # Pour les autres modes
            self.current_path = self.current_connection.get('root_path', '/')
        
        # Charger le contenu initial
        self.refresh_current_location()
        
        self.status_label.setText(f"✅ Connecté en mode {self.current_mode}")
    
    def refresh_current_location(self):
        """Actualise le contenu de l'emplacement actuel"""
        if not self.session:
            return
        
        self.status_label.setText("🔄 Chargement du contenu...")
        
        try:
            if self.current_mode == "webdav" or self.current_mode == "nextcloud_share":
                self.refresh_webdav_content()
            elif self.current_mode == "http_html":
                self.refresh_html_content()
            elif self.current_mode == "geopackage":
                self.refresh_geopackage_content()
            else:
                raise Exception(f"Mode {self.current_mode} non supporté")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur de chargement:\n{str(e)}")
            self.status_label.setText("❌ Erreur de chargement")
    
    def refresh_webdav_content(self):
        """Actualise le contenu WebDAV"""
        # Construire l'URL correctement en évitant les doubles chemins
        base_url = self.current_connection['url'].rstrip('/')
        
        # Pour les liens partagés, utiliser l'URL WebDAV spéciale si disponible
        if self.current_mode == "nextcloud_share":
            if 'webdav_url' in self.current_connection:
                base_url = self.current_connection['webdav_url'].rstrip('/')
                self.status_label.setText(f"📂 Utilisation de l'URL WebDAV pour lien partagé: {base_url}")
                print(f"⚡ URL WebDAV pour lien partagé: {base_url}, chemin actuel: {self.current_path}")
            else:
                # Si webdav_url n'est pas configuré, essayer de le créer
                if self.is_nextcloud_shared_link():
                    share_info = self.get_nextcloud_share_info()
                    if share_info:
                        self.current_connection['webdav_url'] = share_info['public_webdav']
                        base_url = share_info['public_webdav'].rstrip('/')
                        self.status_label.setText(f"📂 URL WebDAV configurée automatiquement: {base_url}")
                        print(f"⚡ URL WebDAV créée pour lien partagé: {base_url}")
                        
                        # Configurer l'authentification si nécessaire
                        self.configure_shared_link_auth()
            
        # Vérifier si l'URL de base contient déjà un chemin complet (cas Nextcloud)
        is_nextcloud = any(indicator in base_url.lower() for indicator in 
                        ['/remote.php/dav/', '/index.php/dav/', '/owncloud/remote.php/', '/public.php/webdav'])
        
        raw_path = self.current_path
        
        # Pour Nextcloud, il faut faire attention à la construction de l'URL
        if is_nextcloud:
            # Cas spécial pour les liens partagés avec public.php/webdav
            if '/public.php/webdav' in base_url and self.current_mode == "nextcloud_share":
                print(f"⚡ Construction d'URL pour lien partagé Nextcloud (public.php/webdav)")
                
                # S'assurer que nous n'avons pas de duplication du segment public.php/webdav
                if base_url.count('/public.php/webdav') > 1:
                    base_url = re.sub(r'(/public\.php/webdav).*', r'\1', base_url)
                    print(f"⚡ URL de base nettoyée: {base_url}")
            
            # Si on est à la racine, utiliser l'URL de base telle quelle
            if self.current_path == '/':
                folder_url = base_url
                clean_path = '/'
            else:
                # Pour les sous-dossiers, ajouter le chemin nettoyé à l'URL de base
                
                # Pour les liens partagés, appliquer la correction spécifique avant
                if self.current_mode == "nextcloud_share" and '/public.php/webdav' in base_url:
                    path_to_clean = self.fix_shared_link_path(self.current_path)
                    clean_path = self.clean_nextcloud_path(path_to_clean)
                    print(f"⚡ Chemin pour lien partagé après correction: {clean_path}")
                else:
                    clean_path = self.clean_nextcloud_path(self.current_path)
                
                # Vérification supplémentaire pour éviter la duplication
                path_parts = clean_path.split('/')
                base_parts = base_url.split('/')
                
                # Détecter les segments communs qui pourraient causer une duplication
                duplicate_segments = [p for p in path_parts if p and p in base_parts]
                
                if duplicate_segments and any(s in ['remote.php', 'index.php', 'owncloud', 'mdrive'] for s in duplicate_segments):
                    # Si on détecte des segments qui pourraient causer une duplication,
                    # reconstruire l'URL différemment selon le cas
                    if 'remote.php' in duplicate_segments:
                        # Cas spécial NextCloud - détecter si remote.php est déjà dans l'URL de base
                        if '/remote.php/' in base_url:
                            # Extraire juste la partie après le dernier /remote.php/dav/files/username/
                            matches = re.findall(r'/remote\.php/dav/files/[^/]+/(.*)', clean_path)
                            if matches:
                                clean_path = '/' + matches[-1]  # Prendre la dernière correspondance
                    
                folder_url = base_url + clean_path
        else:
            # Pour les autres serveurs WebDAV, construire l'URL normalement
            clean_path = raw_path if raw_path.startswith('/') else '/' + raw_path
            folder_url = base_url + clean_path
        
        # Dernière vérification anti-duplication pour 'public.php/webdav'
        if 'public.php/webdav/public.php/webdav' in folder_url:
            print("⚠️ Détection de duplication 'public.php/webdav' dans l'URL finale!")
            folder_url = folder_url.replace('public.php/webdav/public.php/webdav', 'public.php/webdav')
            print(f"⚡ URL corrigée: {folder_url}")
        
        # Débogage de la construction de l'URL
        self.debug_url_construction("refresh_webdav_content", raw_path, clean_path, folder_url)
        
        # Dernière vérification - nettoyage sanitaire de l'URL
        folder_url = self.sanitize_webdav_url(folder_url)
        
        # Vérifier que l'URL est valide
        if not folder_url or not isinstance(folder_url, str):
            raise Exception(f"URL invalide après sanitization: {folder_url}")
        
        # Vérification supplémentaire de l'URL
        if not folder_url.startswith('http'):
            folder_url = 'https://' + folder_url.lstrip('/')
            print(f"⚠️ Ajout du protocole HTTPS à l'URL: {folder_url}")
        
        # S'assurer que l'URL a un format correct avec double slash après le protocole
        if '://' not in folder_url:
            folder_url = folder_url.replace(':/','://')
            print(f"⚠️ Correction format protocole: {folder_url}")
            
        self.status_label.setText(f"🔄 Chargement du contenu depuis {folder_url}...")
        
        try:
            # Afficher l'URL finale pour débogage
            print(f"⚡ URL FINALE pour PROPFIND: {folder_url}")
            
            response = self.session.request('PROPFIND', folder_url,
                                        headers={'Depth': '1'},
                                        timeout=30)
            
            if response.status_code == 207:
                items = self.parse_webdav_response(response.text)
                self.populate_content_table(items)
                self.update_navigation_ui()
                self.status_label.setText(f"✅ {len(items)} éléments chargés")
            else:
                raise Exception(f"Erreur WebDAV {response.status_code} - URL: {folder_url}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur de chargement WebDAV:\n{str(e)}")
            self.status_label.setText(f"❌ Échec: {str(e)}")
    
    def parse_webdav_response(self, xml_content):
        """Parse la réponse WebDAV et identifie les types de fichiers"""
        items = []
        
        try:
            root = ET.fromstring(xml_content)
            base_url = self.current_connection['url'].rstrip('/')
            
            for response in root.findall('.//{DAV:}response'):
                href = response.find('.//{DAV:}href')
                propstat = response.find('.//{DAV:}propstat')
                
                if href is not None and propstat is not None:
                    # Obtenir le chemin brut et le nettoyer
                    raw_path = unquote(href.text)
                    
                    # Nettoyer le chemin pour éviter les doublons de Nextcloud
                    path = self.clean_nextcloud_path(raw_path)
                    
                    # Garder une trace du chemin d'origine pour les URLs absolues
                    is_absolute_url = raw_path.startswith('http')
                    
                    # Extraire le chemin relatif pour les comparaisons
                    relative_path = path
                    
                    # Ignorer le dossier parent
                    current_path_no_slash = self.current_path.rstrip('/')
                    relative_path_no_slash = relative_path.rstrip('/')
                    
                    if relative_path_no_slash == current_path_no_slash or path == self.current_path:
                        continue
                    
                    props = propstat.find('.//{DAV:}prop')
                    if props is not None:
                        item = self.extract_item_info(raw_path, props)
                        if item:
                            # S'assurer que l'item a un chemin nettoyé pour la navigation
                            item['clean_path'] = path
                            items.append(item)
            
        except ET.ParseError as e:
            raise Exception(f"Erreur parsing XML: {str(e)}")
        
        return items
    
    def extract_item_info(self, file_path, props):
        """Extrait les informations d'un élément avec détection de type"""
        try:
            base_url = self.current_connection['url'].rstrip('/')
            raw_path = file_path  # Conserver le chemin d'origine pour le débogage
            
            # Nettoyer le chemin pour éviter les duplications
            clean_path = self.clean_nextcloud_path(file_path)
            
            # Déterminer si le chemin est déjà une URL complète
            is_absolute_url = file_path.startswith('http')
            
            # Déterminer le nom du fichier/dossier
            name = ""
            if file_path.endswith('/'):
                # C'est un dossier
                parts = file_path.rstrip('/').split('/')
                name = parts[-1] if parts else ""
            else:
                # C'est un fichier
                name = file_path.split('/')[-1]
            
            # Déterminer si c'est un dossier
            resourcetype = props.find('.//{DAV:}resourcetype')
            is_folder = resourcetype is not None and resourcetype.find('.//{DAV:}collection') is not None
            
            # Propriétés de base
            size_elem = props.find('.//{DAV:}getcontentlength')
            size = int(size_elem.text) if size_elem is not None and size_elem.text else 0
            
            date_elem = props.find('.//{DAV:}getlastmodified')
            date = date_elem.text if date_elem is not None else ""
            
            content_type_elem = props.find('.//{DAV:}getcontenttype')
            content_type = content_type_elem.text if content_type_elem is not None else ""
            
            # Détection du type de fichier
            file_extension = ""
            file_info = None
            description = ""
            
            if not is_folder:
                file_extension = PyPath(name).suffix.lower()
                file_info = self.file_handlers.get(file_extension, {
                    'type': 'unknown', 'icon': 'file', 'handler': self.handle_generic_file
                })
                description = self.get_file_description(file_info['type'], size)
            else:
                file_info = {'type': 'folder', 'icon': 'folder', 'handler': self.handle_folder}
                description = "Dossier"
            
            # Construire l'URL complète en évitant les duplications
            if is_absolute_url:
                # Si c'est déjà une URL complète, la nettoyer
                item_url = file_path
                # Si elle commence par notre URL de base, la remplacer pour éviter les duplications
                if item_url.startswith(base_url):
                    relative_part = clean_path
                    item_url = base_url + relative_part
            else:
                # Pour les chemins relatifs
                item_url = base_url + clean_path
            
            # Débogage de la construction d'URL
            self.debug_url_construction("extract_item_info", raw_path, clean_path, item_url)
            
            return {
                'name': name,
                'path': clean_path,  # Stocker le chemin nettoyé pour la navigation
                'full_path': file_path, # Conserver le chemin complet original
                'is_folder': is_folder,
                'size': size,
                'size_formatted': self.format_size(size) if not is_folder else "",
                'date': date,
                'content_type': content_type,
                'extension': file_extension,
                'file_type': file_info['type'],
                'icon_type': file_info['icon'],
                'handler': file_info['handler'],
                'description': description,
                'url': item_url,
                'clean_path': clean_path,
                'is_absolute_url': is_absolute_url
            }
            
        except Exception as e:
            print(f"Erreur extraction item: {e}")
            return None
    
    def get_file_description(self, file_type, size):
        """Génère une description du fichier selon son type"""
        descriptions = {
            'raster': f"Image géoréférencée ({self.format_size(size)})",
            'vector': f"Données vectorielles ({self.format_size(size)})",
            'geopackage': f"Base de données géographiques ({self.format_size(size)})",
            'database': f"Base de données ({self.format_size(size)})",
            'archive': f"Archive compressée ({self.format_size(size)})",
            'qgis_project': f"Projet QGIS ({self.format_size(size)})",
            'metadata': f"Métadonnées ({self.format_size(size)})",
            'html_debug': f"Contenu HTML ({self.format_size(size)})",
            'unknown': f"Fichier ({self.format_size(size)})"
        }
        return descriptions.get(file_type, f"Fichier {file_type} ({self.format_size(size)})")
    
    def format_size(self, size_bytes):
        """Formate une taille en unité lisible"""
        if size_bytes == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
    
    def populate_content_table(self, items):
        """Remplit la table avec les éléments détectés"""
        # Sauvegarder pour filtrage
        self.current_items = items
        
        # Appliquer les filtres
        self.apply_filter()
    
    def apply_filter(self):
        """Applique les filtres sur les éléments"""
        if not hasattr(self, 'current_items'):
            return
        
        filter_type = self.filter_combo.currentText()
        search_text = self.search_edit.text().lower()
        
        # Filtrer les éléments
        filtered_items = []
        
        for item in self.current_items:
            # Filtre par type
            show_item = True
            
            if filter_type == "Dossiers seulement":
                show_item = item['is_folder']
            elif filter_type == "Fichiers géographiques":
                show_item = item['file_type'] in ['raster', 'vector', 'geopackage']
            elif filter_type == "Archives et bases":
                show_item = item['file_type'] in ['archive', 'database', 'geopackage']
            elif filter_type == "Images raster":
                show_item = item['file_type'] == 'raster'
            elif filter_type == "Données vecteur":
                show_item = item['file_type'] == 'vector'
            elif filter_type == "Projets QGIS":
                show_item = item['file_type'] == 'qgis_project'
            
            # Filtre par recherche
            if show_item and search_text:
                searchable = f"{item['name']} {item['description']}".lower()
                show_item = search_text in searchable
            
            if show_item:
                filtered_items.append(item)
        
        # Mettre à jour la table
        self.update_content_table(filtered_items)
        
        # Statistiques
        total = len(self.current_items) if hasattr(self, 'current_items') else 0
        shown = len(filtered_items)
        
        if total != shown:
            self.stats_label.setText(f"📊 Éléments: {shown} affichés / {total} total")
        else:
            self.stats_label.setText(f"📊 Éléments: {total}")
    
    def update_content_table(self, items):
        """Met à jour la table avec les éléments filtrés"""
        self.content_table.setRowCount(len(items))
        
        for i, item in enumerate(items):
            # Icône et nom
            name_item = QTableWidgetItem(item['name'])
            name_item.setData(Qt.UserRole, item)  # Stocker les données complètes
            
            # Icône selon le type
            icon = self.get_icon_for_type(item['icon_type'])
            if icon:
                name_item.setIcon(icon)
            
            self.content_table.setItem(i, 0, name_item)
            
            # Type avec couleur
            type_item = QTableWidgetItem(item['file_type'].title())
            type_item.setForeground(self.get_color_for_type(item['file_type']))
            self.content_table.setItem(i, 1, type_item)
            
            # Taille
            self.content_table.setItem(i, 2, QTableWidgetItem(item['size_formatted']))
            
            # Date
            self.content_table.setItem(i, 3, QTableWidgetItem(item['date']))
            
            # Description
            self.content_table.setItem(i, 4, QTableWidgetItem(item['description']))
            
            # Action suggérée
            action = self.get_suggested_action(item)
            self.content_table.setItem(i, 5, QTableWidgetItem(action))
        
        # Ajuster les colonnes
        self.content_table.resizeColumnsToContents()
    
    def get_icon_for_type(self, icon_type):
        """Retourne l'icône appropriée pour un type"""
        icon_map = {
            'folder': QStyle.SP_DirIcon,
            'raster': QStyle.SP_FileIcon,  # Idéalement une icône raster
            'vector': QStyle.SP_FileIcon,  # Idéalement une icône vecteur
            'database': QStyle.SP_DriveHDIcon,
            'archive': QStyle.SP_FileIcon,
            'project': QStyle.SP_FileIcon,
            'text': QStyle.SP_FileDialogDetailedView,
            'file': QStyle.SP_FileIcon
        }
        
        standard_icon = icon_map.get(icon_type, QStyle.SP_FileIcon)
        return self.style().standardIcon(standard_icon)
    
    def get_color_for_type(self, file_type):
        """Retourne la couleur appropriée pour un type"""
        color_map = {
            'folder': QColor('blue'),
            'raster': QColor('green'),
            'vector': QColor('purple'),
            'geopackage': QColor('darkblue'),
            'database': QColor('darkblue'),
            'archive': QColor('orange'),
            'qgis_project': QColor('darkgreen'),
            'metadata': QColor('gray'),
            'html_debug': QColor('brown'),
            'unknown': QColor('black')
        }
        
        return color_map.get(file_type, QColor('black'))
    
    def get_suggested_action(self, item):
        """Retourne l'action suggérée pour un élément"""
        if item['is_folder']:
            return "Double-clic → Ouvrir"
        
        action_map = {
            'raster': "Double-clic → Charger",
            'vector': "Double-clic → Charger", 
            'geopackage': "Double-clic → Explorer",
            'database': "Double-clic → Explorer",
            'archive': "Double-clic → Examiner",
            'qgis_project': "Double-clic → Ouvrir",
            'metadata': "Double-clic → Lire",
            'html_debug': "Double-clic → Voir HTML"
        }
        
        return action_map.get(item['file_type'], "Clic droit → Options")
    
    def update_navigation_ui(self):
        """Met à jour l'interface de navigation"""
        # Chemin
        self.path_label.setText(f"📍 Chemin: {self.current_path}")
        
        # Mode
        mode_icons = {
            'webdav': '🌐',
            'http_html': '📄', 
            'http_direct': '🔗',
            'geopackage': '🗄️'
        }
        
        mode_icon = mode_icons.get(self.current_mode, '📁')
        self.mode_label.setText(f"{mode_icon} {self.current_mode.title()}")
        
        # Boutons de navigation
        self.up_btn.setEnabled(self.current_path != "/" and self.current_mode in ["webdav", "http_html"])
        self.back_btn.setEnabled(hasattr(self, 'navigation_history') and len(self.navigation_history) > 1)
    
    def on_selection_changed(self):
        """Gère le changement de sélection"""
        selected_items = self.content_table.selectedItems()
        
        if selected_items:
            # Prendre la première ligne sélectionnée
            row = selected_items[0].row()
            item_data = self.content_table.item(row, 0).data(Qt.UserRole)
            
            if item_data:
                # Activer les boutons appropriés
                self.open_btn.setEnabled(True)
                
                can_load = item_data['file_type'] in ['raster', 'vector', 'qgis_project']
                self.load_btn.setEnabled(can_load)
                
                self.download_btn.setEnabled(not item_data['is_folder'])
                
                # Mettre à jour l'aperçu
                if self.auto_preview_check.isChecked():
                    self.update_preview(item_data)
                
                # Actions spécialisées
                self.update_specialized_actions(item_data)
        else:
            # Désactiver les boutons
            self.open_btn.setEnabled(False)
            self.load_btn.setEnabled(False) 
            self.download_btn.setEnabled(False)
            self.preview_text.clear()
            self.clear_specialized_actions()
    
    def update_preview(self, item):
        """Met à jour l'aperçu d'un élément"""
        preview_html = f"""
<b>{item['name']}</b><br>
<b>Type:</b> {item['file_type'].title()}<br>
<b>Taille:</b> {item['size_formatted']}<br>
<b>Date:</b> {item['date']}<br>
<b>Description:</b> {item['description']}<br>
        """
        
        if item['extension']:
            preview_html += f"<b>Extension:</b> {item['extension']}<br>"
        
        if item['content_type']:
            preview_html += f"<b>Type MIME:</b> {item['content_type']}<br>"
        
        preview_html += f"<br><b>URL:</b><br><small>{item['url']}</small>"
        
        self.preview_text.setHtml(preview_html)
    
    def update_specialized_actions(self, item):
        """Met à jour les actions spécialisées selon le type"""
        self.clear_specialized_actions()
        
        if item['file_type'] == 'geopackage':
            explore_btn = QPushButton("🔍 Explorer contenu GeoPackage")
            explore_btn.clicked.connect(lambda: self.explore_geopackage(item))
            self.specialized_actions.addWidget(explore_btn)
        
        elif item['file_type'] == 'archive':
            examine_btn = QPushButton("📦 Examiner archive")
            examine_btn.clicked.connect(lambda: self.examine_archive(item))
            self.specialized_actions.addWidget(examine_btn)
        
        elif item['file_type'] == 'metadata':
            read_btn = QPushButton("📄 Lire métadonnées")
            read_btn.clicked.connect(lambda: self.read_metadata(item))
            self.specialized_actions.addWidget(read_btn)
    
    def clear_specialized_actions(self):
        """Efface les actions spécialisées"""
        while self.specialized_actions.count():
            child = self.specialized_actions.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def on_item_double_clicked(self, item):
        """Gère le double-clic sur un élément"""
        item_data = item.data(Qt.UserRole)
        if item_data:
            # Appeler le handler approprié
            item_data['handler'](item_data)
    
    # === HANDLERS POUR DIFFÉRENTS TYPES DE FICHIERS ===
    
    def handle_folder(self, folder_data):
        """Gère l'ouverture d'un dossier"""
        try:
            if self.current_mode == "webdav" or self.current_mode == "nextcloud_share":
                # Utiliser le chemin nettoyé si disponible, sinon le nettoyer nous-mêmes
                if 'clean_path' in folder_data:
                    clean_path = folder_data['clean_path']
                else:
                    clean_path = self.clean_nextcloud_path(folder_data['path'])
                
                # Debug pour liens partagés
                if self.current_mode == "nextcloud_share":
                    print(f"⚡ Ouverture dossier dans lien partagé: path={folder_data['path']}, clean_path={clean_path}")
                    self.status_label.setText(f"📁 Navigation dans lien partagé: {clean_path}")
                    
                self.navigate_to_path(clean_path)
            elif self.current_mode == "http_html":
                # Pour HTML, url contient l'URL complète
                self.navigate_to_html_url(folder_data['url'])
            else:
                self.navigate_to_path(folder_data['path'])
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le dossier:\n{str(e)}")
            self.status_label.setText(f"❌ Erreur ouverture dossier: {str(e)}")
    
    def navigate_to_html_url(self, url):
        """Navigue vers une URL HTML spécifique"""
        # Extraire le chemin relatif depuis l'URL
        base_url = self.current_connection['url'].rstrip('/')
        
        if url.startswith(base_url):
            relative_path = url[len(base_url):]
            if not relative_path.startswith('/'):
                relative_path = '/' + relative_path
            self.current_path = relative_path
        else:
            # URL externe, l'utiliser telle quelle
            self.current_path = url
        
        self.refresh_current_location()
    
    def handle_raster_file(self, file_data):
        """Gère un fichier raster"""
        # Cas spécial pour CRAIG et autres liens de partage Nextcloud
        base_url = self.current_connection.get('url', '').lower()
        
        # Pour le CRAIG, utiliser notre fonction ultra-spécialisée avec le format d'URL exact
        if '/s/opendata' in base_url:
            extension = PyPath(file_data['name']).suffix.lower()
            if extension in ['.tif', '.tiff']:
                self.status_label.setText("🔄 Utilisation de la méthode spéciale CRAIG...")
                return self.load_craig_raster(file_data)
                
        # Pour les autres liens partagés avec limitation de requêtes, utiliser le téléchargement local
        elif '/s/' in base_url:
            extension = PyPath(file_data['name']).suffix.lower()
            if extension in ['.tif', '.tiff', '.jpg', '.png', '.jp2']:
                self.status_label.setText("🔄 Utilisation du téléchargement local pour éviter erreur 429...")
                return self.load_raster_file_with_download(file_data)
            
        # Méthode standard pour les autres cas
        self.load_geographic_file(file_data, 'raster')
    
    def handle_vector_file(self, file_data):
        """Gère un fichier vecteur"""
        self.load_geographic_file(file_data, 'vector')
    
    def handle_geopackage_file(self, file_data):
        """Gère un fichier GeoPackage - c'est ici que la magie opère !"""
        self.explore_geopackage(file_data)
    
    def handle_database_file(self, file_data):
        """Gère une base de données"""
        # Essayer de l'ouvrir comme GeoPackage d'abord
        self.explore_geopackage(file_data)
    
    def handle_archive_file(self, file_data):
        """Gère une archive"""
        self.examine_archive(file_data)
    
    def handle_qgis_project(self, file_data):
        """Gère un projet QGIS stocké sur WebDAV"""
        try:
            # Proposer deux options: chargement direct ou téléchargement puis chargement
            options = [
                "Ouvrir directement depuis WebDAV (lecture seule)",
                "Télécharger localement puis ouvrir (modifications possibles)"
            ]
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Ouvrir le projet QGIS - {file_data['name']}")
            dialog.setMinimumWidth(400)
            
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("Comment souhaitez-vous ouvrir ce projet QGIS ?"))
            
            # Options avec explications
            option_group = QButtonGroup(dialog)
            option1 = QRadioButton(options[0])
            option2 = QRadioButton(options[1])
            option1.setChecked(True)  # Option par défaut
            option_group.addButton(option1)
            option_group.addButton(option2)
            
            layout.addWidget(option1)
            layout.addWidget(QLabel("    Le projet sera ouvert en lecture seule directement depuis le serveur WebDAV."))
            layout.addWidget(option2)
            layout.addWidget(QLabel("    Le projet sera d'abord téléchargé sur votre machine puis ouvert."))
            layout.addWidget(QLabel("    Les modifications seront possibles mais n'affecteront que votre copie locale."))
            
            # Avertissement
            warning = QLabel("⚠️ Attention : Cette action fermera le projet actuellement ouvert !")
            warning.setStyleSheet("color: red; font-weight: bold;")
            layout.addWidget(warning)
            
            # Boutons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec_() != QDialog.Accepted:
                return
            
            # Nettoyer l'URL pour éviter les duplications
            raw_url = file_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Option sélectionnée
            direct_mode = option1.isChecked()
            
            if direct_mode:
                # Ouverture directe depuis WebDAV
                self.status_label.setText(f"🔄 Ouverture du projet QGIS depuis WebDAV...")
                
                # Configurer l'authentification si nécessaire
                username = self.current_connection.get('username', '')
                password = self.current_connection.get('password', '')
                if username and password:
                    import os
                    os.environ['GDAL_HTTP_USERPWD'] = f"{username}:{password}"
                    os.environ['GDAL_HTTP_AUTH'] = 'BASIC'
                
                # Construction de l'URL avec vsicurl
                project_url = f"/vsicurl/{clean_url}"
                
                print(f"⚡ Ouverture du projet QGIS depuis: {project_url}")
                
                # Demander confirmation une dernière fois
                reply = QMessageBox.question(self, "Confirmer l'ouverture", 
                                          f"Êtes-vous sûr de vouloir ouvrir le projet QGIS ?\n\n"
                                          f"📁 {file_data['name']}\n\n"
                                          f"⚠️ Le projet actuel sera fermé.",
                                          QMessageBox.Yes | QMessageBox.No,
                                          QMessageBox.Yes)
                
                if reply == QMessageBox.Yes:
                    # Ouverture du projet
                    QgsProject.instance().read(project_url)
                    self.status_label.setText(f"✅ Projet QGIS ouvert: {file_data['name']} (lecture seule)")
                    
                    QMessageBox.information(self, "Projet ouvert", 
                                         f"Le projet a été ouvert en lecture seule.\n\n"
                                         f"Pour enregistrer des modifications, utilisez 'Enregistrer sous...' "
                                         f"pour créer une copie locale.")
            else:
                # Télécharger puis ouvrir
                self.status_label.setText(f"🔄 Téléchargement du projet QGIS...")
                
                # Demander où enregistrer le projet
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Enregistrer le projet QGIS", 
                    file_data['name'],
                    "Projets QGIS (*.qgz *.qgs)"
                )
                
                if not file_path:
                    return
                
                # Télécharger le fichier
                try:
                    # Informations d'authentification
                    username = self.current_connection.get('username', '')
                    password = self.current_connection.get('password', '')
                    
                    # Créer une session avec authentification
                    import requests
                    session = requests.Session()
                    if username and password:
                        session.auth = (username, password)
                    
                    self.status_label.setText(f"🔄 Téléchargement de {file_data['name']}...")
                    response = session.get(clean_url, stream=True, timeout=60)
                    
                    if response.status_code != 200:
                        raise Exception(f"Erreur HTTP {response.status_code}")
                    
                    # Enregistrer le fichier
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # Ouvrir le projet téléchargé
                    self.status_label.setText(f"🔄 Ouverture du projet QGIS local...")
                    QgsProject.instance().read(file_path)
                    self.status_label.setText(f"✅ Projet QGIS ouvert: {file_data['name']}")
                    
                    QMessageBox.information(self, "Projet ouvert", 
                                         f"Le projet a été téléchargé et ouvert depuis:\n{file_path}\n\n"
                                         f"Vous pouvez maintenant effectuer des modifications et les enregistrer.")
                    
                except Exception as e:
                    error_msg = str(e)
                    QMessageBox.critical(self, "Erreur", f"Impossible de télécharger le projet QGIS:\n{error_msg}")
                    self.status_label.setText(f"❌ Erreur: {error_msg}")
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le projet QGIS:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
    
    def handle_metadata_file(self, file_data):
        """Gère un fichier de métadonnées"""
        self.read_metadata(file_data)
    
    def handle_generic_file(self, file_data):
        """Gère un fichier générique"""
        # Proposer téléchargement ou tentative de chargement QGIS
        reply = QMessageBox.question(self, "Fichier inconnu", 
                                   f"Que faire avec ce fichier ?\n\n"
                                   f"📄 {file_data['name']}\n"
                                   f"🏷️ Type: {file_data['file_type']}",
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.Yes)
        
        if reply == QMessageBox.Yes:
            # Essayer de le charger dans QGIS
            self.load_geographic_file(file_data, 'unknown')
    
    # === MÉTHODES SPÉCIALISÉES ===
    
    def explore_geopackage(self, geopackage_data):
        """Explore le contenu d'un GeoPackage - FONCTIONNALITÉ CLÉ !"""
        self.status_label.setText("📥 Téléchargement et analyse du GeoPackage...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            # Importer les modules nécessaires
            import os, tempfile
            
            # Nettoyer l'URL pour éviter les duplications
            raw_url = geopackage_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            print(f"⚡ Téléchargement du GeoPackage depuis: {clean_url}")
            
            # Informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            
            # Créer une session avec authentification
            import requests
            session = requests.Session()
            if username and password:
                session.auth = (username, password)
            
            # Définir l'en-tête User-Agent
            session.headers.update({
                'User-Agent': 'QGIS-WebDAV-Explorer/1.0'
            })
            
            # Télécharger le GeoPackage
            response = session.get(clean_url, stream=True, timeout=120)
            
            if response.status_code != 200:
                raise Exception(f"Erreur téléchargement: {response.status_code}")
            
            # Sauvegarder temporairement
            with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp_file:
                # Indiquer la progression
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                # Configurer la barre de progression
                if total_size > 0:
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setValue(0)
                
                # Écrire le fichier par morceaux
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                        downloaded += len(chunk)
                        
                        # Mettre à jour la progression si possible
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_bar.setValue(progress)
                            self.status_label.setText(f"📥 Téléchargement: {progress}%")
                
                gpkg_path = tmp_file.name
            
            print(f"⚡ GeoPackage téléchargé dans: {gpkg_path}")
            self.status_label.setText("🔍 Analyse du GeoPackage...")
            
            # Analyser avec QGIS
            layer = QgsVectorLayer(gpkg_path, geopackage_data['name'], "ogr")
            
            if not layer.isValid():
                # Essayer de lister manuellement les tables
                import sqlite3
                conn = sqlite3.connect(gpkg_path)
                cursor = conn.cursor()
                
                # Vérifier si c'est bien un GeoPackage
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gpkg_contents'")
                    if not cursor.fetchone():
                        raise Exception("Le fichier ne semble pas être un GeoPackage valide")
                    
                    # Lister les couches disponibles
                    cursor.execute("SELECT table_name FROM gpkg_contents")
                    tables = cursor.fetchall()
                    
                    if not tables:
                        raise Exception("Aucune table trouvée dans le GeoPackage")
                        
                    print(f"⚡ Tables trouvées dans le GeoPackage: {[t[0] for t in tables]}")
                    
                    # Essayer de charger la première couche
                    first_table = tables[0][0]
                    layer = QgsVectorLayer(f"{gpkg_path}|layername={first_table}", first_table, "ogr")
                    
                    if not layer.isValid():
                        raise Exception(f"Impossible de charger la couche '{first_table}'")
                        
                except sqlite3.Error as e:
                    raise Exception(f"Erreur SQL: {e}")
                finally:
                    conn.close()
            
            # Extraire les données
            geopackage_items = self.extract_geopackage_content(layer, geopackage_data, gpkg_path)
            
            # Passer en mode GeoPackage
            self.switch_to_geopackage_mode(geopackage_data, geopackage_items, gpkg_path)
            
            self.status_label.setText(f"✅ GeoPackage exploré: {len(geopackage_items)} éléments")
            
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur GeoPackage", 
                               f"Impossible d'explorer le GeoPackage:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur exploration GeoPackage: {error_msg}")
        
        finally:
            self.progress_bar.setVisible(False)
    
    def extract_geopackage_content(self, layer, geopackage_data, gpkg_path=None):
        """Extrait le contenu d'un GeoPackage analysé"""
        items = []
        
        try:
            # Importer les modules nécessaires
            import os, sqlite3
            
            # Informations sur la couche
            feature_count = layer.featureCount()
            fields = layer.fields()
            
            # Lister toutes les couches du GeoPackage
            layers = []
            
            # Si un chemin de fichier est fourni, explorer toutes les couches
            if gpkg_path:
                conn = sqlite3.connect(gpkg_path)
                cursor = conn.cursor()
                
                try:
                    cursor.execute("SELECT table_name, data_type FROM gpkg_contents")
                    tables = cursor.fetchall()
                    
                    for table_name, data_type in tables:
                        layers.append({
                            'name': table_name,
                            'type': data_type
                        })
                except sqlite3.Error as e:
                    print(f"⚠️ Erreur SQL: {e}")
                finally:
                    conn.close()
            
            # Ajouter chaque couche comme un "item virtuel"
            for layer_info in layers:
                layer_name = layer_info['name']
                layer_type = layer_info['type']
                
                # Déterminer le type d'icône
                icon_type = 'vector'
                if layer_type == 'features':
                    icon_type = 'vector'
                elif layer_type == 'tiles':
                    icon_type = 'raster'
                else:
                    icon_type = 'database'
                
                # Créer l'item
                item = {
                    'name': layer_name,
                    'path': f"geopackage://{geopackage_data['name']}/{layer_name}",
                    'is_folder': False,
                    'size': 0,
                    'size_formatted': "",
                    'date': "",
                    'content_type': "application/geopackage",
                    'extension': '.gpkg',
                    'file_type': 'geopackage_layer',
                    'icon_type': icon_type,
                    'handler': lambda item_data, layer_name=layer_name: self.handle_geopackage_layer(item_data, layer_name, gpkg_path),
                    'description': f"Couche {layer_type} du GeoPackage",
                    'url': geopackage_data['url'],
                    'parent_geopackage': geopackage_data,
                    'gpkg_path': gpkg_path
                }
                
                items.append(item)
            
            # Si aucune couche n'a été trouvée dans la base, analyser quelques features pour le débogage
            if not layers:
                # Analyser quelques features pour déterminer la structure
                sample_features = list(layer.getFeatures())[:10]
                
                for i, feature in enumerate(sample_features):
                    attrs = feature.attributes()
                    
                    # Créer un "item virtuel" pour chaque feature intéressant
                    feature_name = f"Feature_{i+1}"
                    
                    # Essayer de trouver un nom dans les attributs
                    for j, field in enumerate(fields):
                        if j < len(attrs) and attrs[j]:
                            field_name = field.name().lower()
                            if any(keyword in field_name for keyword in ['nom', 'name', 'label', 'id']):
                                feature_name = str(attrs[j])
                                break
                    
                    # Créer l'item
                    item = {
                        'name': feature_name,
                        'path': f"geopackage://{geopackage_data['name']}/feature_{i}",
                        'is_folder': False,
                        'size': 0,
                        'size_formatted': "",
                        'date': "",
                        'content_type': "application/geopackage",
                        'extension': '.gpkg',
                        'file_type': 'geopackage_feature',
                        'icon_type': 'vector',
                        'handler': lambda item_data, feature=feature: self.handle_geopackage_feature(item_data, feature),
                        'description': f"Élément du GeoPackage",
                        'url': geopackage_data['url'],
                        'feature_data': feature,
                        'parent_geopackage': geopackage_data,
                        'gpkg_path': gpkg_path
                    }
                    
                    items.append(item)
            
            # Ajouter des informations générales sur le GeoPackage
            summary_item = {
                'name': f"📊 Résumé GeoPackage ({len(layers) or feature_count} éléments)",
                'path': f"geopackage://{geopackage_data['name']}/summary",
                'is_folder': False,
                'size': geopackage_data['size'],
                'size_formatted': geopackage_data['size_formatted'],
                'date': geopackage_data['date'],
                'content_type': "application/geopackage+summary",
                'extension': '.gpkg',
                'file_type': 'geopackage_summary',
                'icon_type': 'database',
                'handler': lambda item_data: self.show_geopackage_summary(layer, geopackage_data, gpkg_path),
                'description': f"Résumé du GeoPackage",
                'url': geopackage_data['url'],
                'layer_data': layer,
                'parent_geopackage': geopackage_data,
                'gpkg_path': gpkg_path
            }
            
            items.insert(0, summary_item)
            
        except Exception as e:
            print(f"⚠️ Erreur extraction GeoPackage: {e}")
            
            # Ajouter au moins un élément pour pouvoir retourner à l'écran précédent
            error_item = {
                'name': f"⚠️ Erreur d'analyse",
                'path': f"geopackage://{geopackage_data['name']}/error",
                'is_folder': False,
                'size': 0,
                'size_formatted': "",
                'date': "",
                'content_type': "application/geopackage+error",
                'extension': '.gpkg',
                'file_type': 'geopackage_error',
                'icon_type': 'file',
                'handler': lambda item_data: QMessageBox.critical(self, "Erreur", f"Erreur d'analyse: {str(e)}"),
                'description': f"Erreur: {str(e)}",
                'url': geopackage_data['url'],
                'parent_geopackage': geopackage_data,
                'gpkg_path': gpkg_path
            }
            
            items.append(error_item)
        
        return items
    
    def switch_to_geopackage_mode(self, geopackage_data, items, gpkg_path=None):
        """Passe en mode exploration de GeoPackage"""
        # Sauvegarder l'état de navigation
        if not hasattr(self, 'navigation_history'):
            self.navigation_history = []
        
        self.navigation_history.append({
            'mode': self.current_mode,
            'path': self.current_path,
            'items': getattr(self, 'current_items', [])
        })
        
        # Basculer en mode GeoPackage
        self.current_mode = "geopackage"
        self.current_geopackage = geopackage_data
        self.current_geopackage_path = gpkg_path  # Sauvegarder le chemin du fichier téléchargé
        self.current_path = f"geopackage://{geopackage_data['name']}"
        
        # Afficher le contenu
        self.current_items = items
        self.apply_filter()
        self.update_navigation_ui()
        
        # Activer le bouton de retour
        self.back_btn.setEnabled(True)
        
    def handle_geopackage_layer(self, item_data, layer_name, gpkg_path):
        """Gère une couche individuelle d'un GeoPackage"""
        try:
            if not gpkg_path:
                raise Exception("Chemin du GeoPackage non disponible")
                
            self.status_label.setText(f"🔄 Chargement de la couche: {layer_name}")
            print(f"⚡ Chargement de la couche {layer_name} depuis {gpkg_path}")
            
            # Construire l'URI de la couche
            layer_uri = f"{gpkg_path}|layername={layer_name}"
            layer = QgsVectorLayer(layer_uri, layer_name, "ogr")
            
            if not layer.isValid():
                # Essayer en tant que couche raster
                layer = QgsRasterLayer(layer_uri, layer_name)
                
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.status_label.setText(f"✅ Couche chargée: {layer_name}")
                return True
            else:
                raise Exception(f"Couche non valide: {layer_name}")
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger la couche:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def show_geopackage_summary(self, layer, geopackage_data, gpkg_path=None):
        """Affiche un résumé du GeoPackage"""
        # Importer les modules nécessaires
        import sqlite3
        
        # Créer un dialogue avec les informations du GeoPackage
        dialog = QDialog(self)
        dialog.setWindowTitle(f"GeoPackage - {geopackage_data['name']}")
        dialog.resize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        try:
            # Informations générales
            summary_html = f"""
<h3>📦 Résumé du GeoPackage</h3>
<table border="1" cellpadding="5">
<tr><th>Propriété</th><th>Valeur</th></tr>
<tr><td><b>Nom</b></td><td>{geopackage_data['name']}</td></tr>
<tr><td><b>Taille</b></td><td>{geopackage_data['size_formatted']}</td></tr>
<tr><td><b>Date</b></td><td>{geopackage_data['date']}</td></tr>
            """
            
            # Si on a le chemin du fichier, ajouter des informations plus détaillées
            if gpkg_path:
                # Extraire des informations avec SQLite
                conn = sqlite3.connect(gpkg_path)
                cursor = conn.cursor()
                
                try:
                    # Compter les tables
                    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    table_count = cursor.fetchone()[0]
                    
                    # Lister les couches spatiales
                    cursor.execute("SELECT COUNT(*) FROM gpkg_contents")
                    layers_count = cursor.fetchone()[0]
                    
                    # Ajouter à la table HTML
                    summary_html += f"""
<tr><td><b>Tables</b></td><td>{table_count}</td></tr>
<tr><td><b>Couches spatiales</b></td><td>{layers_count}</td></tr>
                    """
                    
                    # Lister les couches
                    cursor.execute("SELECT table_name, data_type FROM gpkg_contents")
                    layers = cursor.fetchall()
                    
                    # Ajouter les couches à la table HTML
                    summary_html += """
</table>
<h4>📋 Couches disponibles</h4>
<table border="1" cellpadding="5">
<tr><th>Nom</th><th>Type</th></tr>
                    """
                    
                    for layer_name, layer_type in layers:
                        summary_html += f"""
<tr><td>{layer_name}</td><td>{layer_type}</td></tr>
                        """
                    
                except sqlite3.Error as e:
                    summary_html += f"""
<tr><td><b>Erreur</b></td><td>{str(e)}</td></tr>
                    """
                finally:
                    conn.close()
            
            summary_html += """
</table>
            """
            
            text_browser = QTextBrowser()
            text_browser.setHtml(summary_html)
            layout.addWidget(text_browser)
            
            # Boutons d'action
            buttons_layout = QHBoxLayout()
            
            # Si on a le chemin local, proposer de charger tout le GeoPackage
            if gpkg_path:
                load_all_btn = QPushButton("📥 Charger toutes les couches")
                load_all_btn.clicked.connect(lambda: (
                    self.load_all_geopackage_layers(gpkg_path, geopackage_data['name']),
                    dialog.accept()
                ))
                buttons_layout.addWidget(load_all_btn)
            else:
                # Sinon, proposer de le télécharger puis charger
                load_all_btn = QPushButton("📥 Télécharger puis charger")
                load_all_btn.clicked.connect(lambda: (
                    self.load_geographic_file(geopackage_data, 'geopackage'),
                    dialog.accept()
                ))
                buttons_layout.addWidget(load_all_btn)
            
            close_btn = QPushButton("Fermer")
            close_btn.clicked.connect(dialog.accept)
            buttons_layout.addWidget(close_btn)
            
            layout.addLayout(buttons_layout)
            
        except Exception as e:
            # En cas d'erreur, afficher un message simple
            error_label = QLabel(f"Erreur lors de l'analyse du GeoPackage: {str(e)}")
            layout.addWidget(error_label)
            
            close_btn = QPushButton("Fermer")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def configure_qgis_auth_for_url(self, url):
        """
        Configure l'authentification QGIS pour une URL spécifique.
        Cela permet à GDAL d'utiliser les gestionnaires d'authentification de QGIS.
        """
        try:
            if not self.current_connection.get('username'):
                return False
                
            from qgis.core import QgsNetworkAccessManager, QgsAuthManager
            
            # Extraire le nom d'hôte de l'URL
            import urllib.parse
            parsed_url = urllib.parse.urlparse(url)
            hostname = parsed_url.netloc
            
            if ':' in hostname:  # Si le port est spécifié
                hostname = hostname.split(':')[0]
                
            # Informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            
            # Configurer l'authentification pour QGIS
            auth_mgr = QgsAuthManager.instance()
            
            # Utiliser la méthode simple d'authentification basique HTTP
            # C'est le plus fiable pour GDAL/vsicurl
            import os
            os.environ['GDAL_HTTP_USERPWD'] = f"{username}:{password}"
            os.environ['GDAL_HTTP_AUTH'] = 'BASIC'
            
            # Configurer aussi le gestionnaire de réseau QGIS
            nam = QgsNetworkAccessManager.instance()
            
            print(f"⚡ Authentification configurée pour l'hôte: {hostname}")
            self.status_label.setText(f"🔐 Authentification configurée pour: {hostname}")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur configuration authentification: {str(e)}")
            return False
    
    def load_geographic_file(self, file_data, file_type_hint):
        """Charge un fichier géographique dans QGIS"""
        try:
            # Importer les modules nécessaires
            import os
            
            # Obtenir l'extension du fichier
            file_extension = PyPath(file_data['name']).suffix.lower()
            
            # Traitement spécifique selon l'extension
            if file_extension == '.shp':
                # Utiliser notre méthode spéciale pour les shapefiles
                return self.load_shapefile_with_dependencies(file_data)
            elif file_extension == '.dbf':
                # Utiliser notre méthode spéciale pour les DBF
                return self.load_dbf_file(file_data)
            elif file_extension == '.gpkg':
                # Pour les GeoPackages, utiliser une approche spécifique
                return self.load_geopackage_file(file_data)
            elif file_extension in ['.csv', '.xls', '.xlsx']:
                # Pour les fichiers CSV et Excel, utiliser notre méthode dédiée
                return self.load_csv_excel_file(file_data)
            elif file_extension == '.py':
                # Pour les scripts Python, utiliser notre méthode dédiée
                return self.load_python_script(file_data)
            elif file_extension in ['.tif', '.tiff', '.jpg', '.png', '.jp2']:
                # Pour les rasters, utiliser notre méthode spéciale pour éviter erreur 429
                # Surtout important pour le CRAIG et autres serveurs avec limitation de requêtes
                if self.is_craig_nextcloud_server() or '/s/' in self.current_connection.get('url', ''):
                    self.status_label.setText("🔄 Utilisation du téléchargement local pour éviter erreur 429...")
                    return self.load_raster_file_with_download(file_data)
            
            # Pour les autres types de fichiers, continuer avec la méthode standard
            # Nettoyer l'URL pour éviter les duplications NextCloud
            raw_url = file_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Obtenir les informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            has_auth = username and password
            
            # Debug avancé - pour résoudre les problèmes d'authentification
            print(f"⚡ Chargement du fichier: {file_data['name']} ({file_type_hint})")
            print(f"⚡ URL nettoyée: {clean_url}")
            print(f"⚡ Authentification disponible: {'Oui' if has_auth else 'Non'}")
            
            # Configuration de l'authentification pour GDAL
            if has_auth:
                # Variables d'environnement pour GDAL
                os.environ['GDAL_HTTP_USERPWD'] = f"{username}:{password}"
                os.environ['GDAL_HTTP_AUTH'] = 'BASIC'
            
            # Construction de l'URL pour GDAL
            layer_source = f"/vsicurl/{clean_url}"
            
            # Déterminer le type de couche à créer
            if file_type_hint == 'raster' or file_extension in ['.tif', '.tiff', '.ecw', '.jp2']:
                self.status_label.setText(f"🔄 Chargement du raster: {file_data['name']}")
                layer = QgsRasterLayer(layer_source, file_data['name'])
                print(f"⚡ Tentative de chargement du raster: {layer_source}")
            else:
                # Pour les autres types, essayer en vecteur d'abord
                self.status_label.setText(f"🔄 Chargement du fichier: {file_data['name']}")
                layer = QgsVectorLayer(layer_source, file_data['name'], "ogr")
                print(f"⚡ Tentative de chargement comme vecteur: {layer_source}")
                
                # Si ça ne marche pas, essayer en raster mais seulement pour certaines extensions
                if not layer.isValid() and file_extension in ['.tif', '.tiff', '.ecw', '.jp2', '.img']:
                    layer = QgsRasterLayer(layer_source, file_data['name'])
                    print(f"⚡ Tentative alternative comme raster: {layer_source}")
            
            # Vérifier si la couche est valide
            if layer.isValid():
                # Gestion des groupes
                if self.create_groups_check.isChecked():
                    root = QgsProject.instance().layerTreeRoot()
                    
                    if hasattr(self, 'current_connection') and self.current_connection:
                        group_name = f"WebDAV - {self.current_connection['name']}"
                    else:
                        group_name = "WebDAV Explorer"
                    
                    group = root.findGroup(group_name)
                    if group is None:
                        group = root.insertGroup(0, group_name)
                    
                    QgsProject.instance().addMapLayer(layer, False)
                    group.addLayer(layer)
                else:
                    QgsProject.instance().addMapLayer(layer)
                
                self.status_label.setText(f"✅ Fichier chargé: {file_data['name']}")
                
                QMessageBox.information(self, "Succès", 
                                      f"Fichier chargé avec succès!\n\n"
                                      f"📄 {file_data['name']}\n"
                                      f"🏷️ Type: {layer.type() == QgsMapLayer.VectorLayer and 'Vecteur' or 'Raster'}")
                
                return True
            else:
                error_msg = layer.error().message() if layer else "Impossible de créer la couche"
                QMessageBox.critical(self, "Erreur QGIS", 
                                   f"Impossible de charger le fichier:\n{error_msg}")
                self.status_label.setText(f"❌ Erreur: {error_msg}")
                return False
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Erreur lors du chargement:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
            
    def load_dbf_file(self, file_data):
        """
        Méthode spéciale pour charger un fichier DBF comme couche tabulaire
        Les DBF peuvent être chargés directement sans fichiers associés
        """
        try:
            # Importer les modules nécessaires
            import os
            
            # Nettoyer l'URL
            raw_url = file_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Configurer l'authentification si nécessaire
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            if username and password:
                os.environ['GDAL_HTTP_USERPWD'] = f"{username}:{password}"
                os.environ['GDAL_HTTP_AUTH'] = 'BASIC'
            
            # Pour les DBF, on peut utiliser directement /vsicurl/ car c'est un fichier unique
            layer_source = f"/vsicurl/{clean_url}"
            layer_name = PyPath(file_data['name']).stem
            
            self.status_label.setText(f"🔄 Chargement du fichier DBF: {file_data['name']}")
            print(f"⚡ Chargement du fichier DBF: {layer_source}")
            
            # Charger comme une couche sans géométrie (tabulaire)
            layer = QgsVectorLayer(layer_source, layer_name, "ogr")
            
            if layer.isValid():
                # Ajouter la couche au projet
                QgsProject.instance().addMapLayer(layer)
                self.status_label.setText(f"✅ Fichier DBF chargé: {file_data['name']}")
                
                QMessageBox.information(self, "Succès", 
                                      f"Fichier DBF chargé avec succès!\n\n"
                                      f"📄 {file_data['name']}")
                return True
            else:
                error_msg = layer.error().message() if hasattr(layer, 'error') and layer.error() else "Couche DBF invalide"
                raise Exception(f"Erreur de chargement DBF: {error_msg}")
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le fichier DBF:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False

    def load_geopackage_file(self, file_data):
        """Méthode spécifique pour charger un GeoPackage"""
        try:
            # Importer les modules nécessaires
            import os
            
            # Nettoyer l'URL
            raw_url = file_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Configurer l'authentification si nécessaire
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            if username and password:
                os.environ['GDAL_HTTP_USERPWD'] = f"{username}:{password}"
                os.environ['GDAL_HTTP_AUTH'] = 'BASIC'
            
            # Construire l'URL pour GDAL
            layer_source = f"/vsicurl/{clean_url}"
            
            # Pour les GeoPackages, proposer de lister les tables disponibles
            self.status_label.setText(f"🔄 Analyse du GeoPackage: {file_data['name']}")
            
            # Utiliser OGR pour lister les couches disponibles
            import os
            os.environ['GDAL_HTTP_USERPWD'] = f"{username}:{password}"
            
            # Créer une couche temporaire pour obtenir la liste des tables
            temp_layer = QgsVectorLayer(layer_source, "temp", "ogr")
            
            if not temp_layer.isValid():
                raise Exception("Impossible d'ouvrir le GeoPackage")
            
            # Lister les sous-couches disponibles
            sublayers = temp_layer.dataProvider().subLayers()
            
            if not sublayers:
                raise Exception("Aucune couche trouvée dans le GeoPackage")
            
            # Si une seule couche, la charger directement
            if len(sublayers) == 1:
                layer_info = sublayers[0].split(":")
                layer_name = layer_info[-1] if len(layer_info) > 1 else file_data['name']
                
                layer_uri = f"{layer_source}|layername={layer_name}"
                layer = QgsVectorLayer(layer_uri, layer_name, "ogr")
                
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    self.status_label.setText(f"✅ GeoPackage chargé: {layer_name}")
                    return True
                else:
                    raise Exception("Couche GeoPackage invalide")
            
            # Si plusieurs couches, afficher un dialogue de sélection
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Sélectionner les couches à charger - {file_data['name']}")
            dialog.resize(500, 400)
            
            layout = QVBoxLayout(dialog)
            
            label = QLabel("Sélectionnez les couches à charger:")
            layout.addWidget(label)
            
            # Liste des couches avec cases à cocher
            list_widget = QListWidget()
            for sublayer in sublayers:
                layer_info = sublayer.split(":")
                layer_name = layer_info[-1] if len(layer_info) > 1 else sublayer
                
                item = QListWidgetItem(layer_name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)  # Coché par défaut
                item.setData(Qt.UserRole, sublayer)  # Stocker les infos complètes
                
                list_widget.addItem(item)
            
            layout.addWidget(list_widget)
            
            # Boutons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            # Exécuter le dialogue
            if dialog.exec_() != QDialog.Accepted:
                return False
            
            # Charger les couches sélectionnées
            loaded_layers = 0
            
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                
                if item.checkState() == Qt.Checked:
                    sublayer_info = item.data(Qt.UserRole)
                    layer_info = sublayer_info.split(":")
                    layer_name = layer_info[-1] if len(layer_info) > 1 else sublayer_info
                    
                    self.status_label.setText(f"🔄 Chargement de la couche: {layer_name}")
                    
                    layer_uri = f"{layer_source}|layername={layer_name}"
                    layer = QgsVectorLayer(layer_uri, layer_name, "ogr")
                    
                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer)
                        loaded_layers += 1
                    else:
                        print(f"⚠️ Couche non valide: {layer_name}")
            
            if loaded_layers > 0:
                self.status_label.setText(f"✅ GeoPackage: {loaded_layers} couches chargées")
                return True
            else:
                raise Exception("Aucune couche valide trouvée dans le GeoPackage")
            
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le GeoPackage:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def navigate_back(self):
        """Retour à l'emplacement précédent"""
        if hasattr(self, 'navigation_history') and self.navigation_history:
            previous_state = self.navigation_history.pop()
            
            self.current_mode = previous_state['mode']
            self.current_path = previous_state['path']
            self.current_items = previous_state['items']
            
            self.apply_filter()
            self.update_navigation_ui()
            
            self.status_label.setText("↩️ Retour effectué")
    
    def navigate_up(self):
        """Navigation vers le dossier parent"""
        if self.current_path != "/" and self.current_mode in ["webdav", "http_html"]:
            path_parts = self.current_path.rstrip('/').split('/')
            if len(path_parts) > 1:
                self.current_path = '/'.join(path_parts[:-1]) + ('/' if len(path_parts) > 2 else '')
            else:
                self.current_path = "/"
            
            self.refresh_current_location()
    
    def navigate_to_path(self, path):
        """Navigue vers un chemin spécifique"""
        # Gestion spéciale pour les liens partagés Nextcloud
        if self.current_mode == "nextcloud_share" and self.is_nextcloud_shared_link():
            self.status_label.setText(f"🔄 Navigation dans un lien partagé Nextcloud: {path}")
            print(f"⚡ Navigation dans un lien partagé: mode={self.current_mode}, path={path}")
            
            # Correction spéciale pour les liens partagés
            path = self.fix_shared_link_path(path)
            print(f"⚡ Chemin après correction spécifique pour lien partagé: {path}")
            
        # Nettoyer le chemin pour éviter les duplications (particulièrement important pour Nextcloud)
        clean_path = self.clean_nextcloud_path(path)
        
        # Si c'est un dossier, s'assurer qu'il y a un slash à la fin
        # sauf pour la racine qui est déjà "/"
        if clean_path != '/':
            clean_path = clean_path.rstrip('/') + '/'
            
        self.current_path = clean_path
        
        # Sauvegarder l'historique de navigation si ce n'est pas déjà fait
        if not hasattr(self, 'navigation_history'):
            self.navigation_history = []
            
        # Ajouter le chemin actuel à l'historique avant de changer
        if not hasattr(self, 'current_path_before_navigation'):
            self.current_path_before_navigation = self.current_path
        else:
            self.navigation_history.append({
                'mode': self.current_mode,
                'path': self.current_path_before_navigation,
                'items': getattr(self, 'current_items', [])
            })
            self.current_path_before_navigation = clean_path
            
        # Rafraîchir avec le nouveau chemin
        self.status_label.setText(f"🔄 Navigation vers {clean_path}...")
        self.refresh_current_location()
    
    # === MÉTHODES D'INTERFACE ===
    
    def open_selected(self):
        """Ouvre l'élément sélectionné"""
        selected_items = self.content_table.selectedItems()
        if selected_items:
            item_data = selected_items[0].data(Qt.UserRole)
            if item_data:
                item_data['handler'](item_data)
    
    def load_selected(self):
        """Charge l'élément sélectionné dans QGIS"""
        selected_items = self.content_table.selectedItems()
        if selected_items:
            item_data = selected_items[0].data(Qt.UserRole)
            if item_data:
                # Pour les rasters dans le CRAIG, utiliser notre méthode spéciale
                if item_data['file_type'] == 'raster' and '/s/opendata' in self.current_connection.get('url', '').lower():
                    extension = PyPath(item_data['name']).suffix.lower()
                    if extension in ['.tif', '.tiff']:
                        self.status_label.setText("🔄 Utilisation de la méthode spéciale CRAIG...")
                        return self.load_craig_raster(item_data)
                
                # Pour les autres types de fichiers, comportement normal
                if item_data['file_type'] in ['raster', 'vector', 'geopackage']:
                    self.load_geographic_file(item_data, item_data['file_type'])
    
    def download_selected(self):
        """Télécharge l'élément sélectionné"""
        selected_items = self.content_table.selectedItems()
        if selected_items:
            item_data = selected_items[0].data(Qt.UserRole)
            if item_data and not item_data['is_folder']:
                # Dialogue de sauvegarde
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Télécharger fichier", 
                    item_data['name'],
                    "Tous les fichiers (*)"
                )
                
                if file_path:
                    self.download_file(item_data, file_path)
    
    def download_file(self, file_data, save_path):
        """Télécharge un fichier vers un emplacement local"""
        self.status_label.setText(f"💾 Téléchargement de {file_data['name']}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        
        try:
            # Pour les liens partagés ou spéciaux, utiliser notre fonction spécialisée
            if self.is_nextcloud_shared_link() or self.is_craig_nextcloud_server():
                clean_url = self.build_download_url(file_data['name'])
                self.status_label.setText(f"💾 Utilisation d'URL adaptée pour lien partagé...")
            else:
                # Méthode standard: nettoyer l'URL pour éviter les duplications
                raw_url = file_data['url']
                clean_url = self.clean_nextcloud_url(raw_url)
            
            # Nous n'avons plus besoin de ce cas spécial car il est déjà géré par build_download_url
            # Le code ci-dessus a été intégré dans build_download_url pour centraliser la logique
            
            # Debug
            print(f"⚡ Téléchargement depuis: {clean_url}")
            
            # Dernière vérification - nettoyage sanitaire de l'URL
            clean_url = self.sanitize_webdav_url(clean_url)
            print(f"⚡ URL FINALE pour téléchargement: {clean_url}")
            
            self.status_label.setText(f"💾 Téléchargement depuis {clean_url}...")
            
            response = self.session.get(clean_url, stream=True, timeout=60)
            
            if response.status_code != 200:
                raise Exception(f"Erreur HTTP {response.status_code} - URL: {clean_url}")
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_bar.setValue(progress)
                        
                        QApplication.processEvents()
            
            self.status_label.setText(f"✅ Téléchargement terminé: {file_data['name']}")
            
            QMessageBox.information(self, "Téléchargement terminé", 
                                  f"Fichier téléchargé avec succès!\n\n"
                                  f"📄 {file_data['name']}\n"
                                  f"💾 Emplacement: {save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur téléchargement", 
                               f"Erreur lors du téléchargement:\n{str(e)}")
            self.status_label.setText(f"❌ Erreur téléchargement: {str(e)}")
        
        finally:
            self.progress_bar.setVisible(False)
    
    def show_context_menu(self, position):
        """Affiche un menu contextuel pour les éléments WebDAV"""
        # Obtenir l'élément sélectionné
        selected_rows = self.content_table.selectedItems()
        
        if selected_rows and hasattr(self, 'current_items'):
            # Élément sélectionné
            row_index = selected_rows[0].row()
            if row_index < len(self.current_items):
                item_data = self.current_items[row_index]
                
                # Créer le menu
                menu = QMenu(self.content_table)
                
                # Déterminer les actions en fonction du type d'élément
                if item_data.get('is_folder', False):
                    # Menu pour les dossiers
                    open_action = menu.addAction("Ouvrir")
                    open_action.triggered.connect(lambda: self.handle_folder(item_data))
                    
                    menu.addSeparator()
                    
                    # Autres actions possibles pour les dossiers...
                    create_folder_action = menu.addAction("Créer un sous-dossier")
                    create_folder_action.triggered.connect(lambda: self.create_folder_in_subfolder(item_data))
                    
                    upload_action = menu.addAction("Téléverser des fichiers ici")
                    upload_action.triggered.connect(lambda: self.upload_file_to_subfolder(item_data))
                    
                else:
                    # Menu pour les fichiers
                    # Déterminer le type de fichier
                    file_extension = os.path.splitext(item_data['name'])[1].lower()
                    
                    # Options pour différents types de fichiers
                    if file_extension in ['.shp', '.gpkg', '.tif', '.geojson', '.kml', '.gml']:
                        # Fichiers géographiques
                        load_action = menu.addAction("Charger comme couche")
                        load_action.triggered.connect(lambda: self.handle_file(item_data))
                        
                    elif file_extension in ['.qgs', '.qgz']:
                        # Projets QGIS
                        open_project_action = menu.addAction("Ouvrir le projet QGIS")
                        open_project_action.triggered.connect(lambda: self.handle_qgis_project(item_data))
                        
                    elif file_extension in ['.csv', '.xls', '.xlsx']:
                        # Fichiers de données tabulaires
                        load_data_action = menu.addAction("Charger comme données")
                        load_data_action.triggered.connect(lambda: self.load_csv_excel_file(item_data))
                        
                    elif file_extension == '.py':
                        # Scripts Python
                        load_script_action = menu.addAction("Charger dans la console Python")
                        load_script_action.triggered.connect(lambda: self.load_python_script(item_data))
                        
                    elif file_extension in ['.zip', '.7z', '.tar', '.gz']:
                        # Archives
                        examine_archive_action = menu.addAction("Examiner l'archive")
                        examine_archive_action.triggered.connect(lambda: self.examine_archive(item_data))
                    
                    # Options communes pour tous les fichiers
                    menu.addSeparator()
                    
                    download_action = menu.addAction("Télécharger")
                    download_action.triggered.connect(lambda: self.download_file(item_data))
                    
                menu.exec_(self.content_table.mapToGlobal(position))
                
        else:
            # Clic dans une zone vide - menu différent
            empty_menu = QMenu(self.content_table)
            
            refresh_action = empty_menu.addAction("Rafraîchir")
            refresh_action.triggered.connect(self.refresh_webdav_content)
            
            empty_menu.addSeparator()
            
            create_folder_action = empty_menu.addAction("Créer un dossier")
            create_folder_action.triggered.connect(self.create_folder_on_webdav)
            
            upload_action = empty_menu.addAction("Téléverser des fichiers")
            upload_action.triggered.connect(self.upload_file_to_webdav)
            
            empty_menu.addSeparator()
            
            save_layer_action = empty_menu.addAction("Enregistrer la couche active")
            save_layer_action.triggered.connect(self.save_current_layer_to_webdav)
            
            save_project_action = empty_menu.addAction("Enregistrer le projet QGIS")
            save_project_action.triggered.connect(self.save_current_project_to_webdav)
            
            empty_menu.exec_(self.content_table.mapToGlobal(position))
            
    def show_item_properties(self, item_data):
        """Affiche les propriétés détaillées d'un élément"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Propriétés - {item_data['name']}")
        dialog.resize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        props_html = f"""
<h3>📋 Propriétés</h3>
<table border="1" cellpadding="5">
<tr><th>Propriété</th><th>Valeur</th></tr>
<tr><td><b>Nom</b></td><td>{item_data['name']}</td></tr>
<tr><td><b>Type</b></td><td>{item_data['file_type'].title()}</td></tr>
<tr><td><b>Taille</b></td><td>{item_data['size_formatted']}</td></tr>
<tr><td><b>Date</b></td><td>{item_data['date']}</td></tr>
<tr><td><b>Extension</b></td><td>{item_data['extension']}</td></tr>
<tr><td><b>Type MIME</b></td><td>{item_data['content_type']}</td></tr>
<tr><td><b>Description</b></td><td>{item_data['description']}</td></tr>
</table>

<h4>🔗 URL d'accès</h4>
<p style="word-break: break-all; font-family: monospace; font-size: 10px;">
{item_data['url']}
</p>
        """
        
        text_browser = QTextBrowser()
        text_browser.setHtml(props_html)
        layout.addWidget(text_browser)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        
        dialog.exec_()
    
    # === GESTION DES CONNEXIONS ===
    
    def show_connection_dialog(self):
        """Affiche le dialogue de nouvelle connexion"""
        from .webdav_connection_dialog import WebDAVConnectionDialog
        
        dialog = WebDAVConnectionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            conn_info = dialog.get_connection_info()
            self.save_connection(conn_info)
            self.load_connections()
            self.connection_combo.setCurrentText(conn_info['name'])
    
    def save_connection(self, conn_info):
        """Sauvegarde une connexion"""
        try:
            settings = QSettings()
            settings.beginGroup("WebDAVGenericExplorer/connections")
            
            conn_name = conn_info['name']
            settings.beginGroup(conn_name)
            for key, value in conn_info.items():
                settings.setValue(key, value)
            settings.endGroup()
            settings.endGroup()
            
            self.connections[conn_name] = conn_info
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur sauvegarde connexion: {e}")
    
    def load_connections(self):
        """Charge les connexions sauvegardées"""
        try:
            settings = QSettings()
            settings.beginGroup("WebDAVGenericExplorer/connections")
            
            self.connections.clear()
            self.connection_combo.clear()
            
            for conn_name in settings.childGroups():
                settings.beginGroup(conn_name)
                
                conn_info = {
                    'name': conn_name,
                    'url': settings.value('url', ''),
                    'username': settings.value('username', ''),
                    'password': settings.value('password', ''),
                    'root_path': settings.value('root_path', '/')
                }
                
                self.connections[conn_name] = conn_info
                self.connection_combo.addItem(conn_name)
                
                settings.endGroup()
            
            settings.endGroup()
            
        except Exception as e:
            print(f"Erreur chargement connexions: {e}")
    
    def on_connection_changed(self, conn_name):
        """Réagit au changement de connexion"""
        if conn_name and conn_name in self.connections:
            self.current_connection = self.connections[conn_name]
            self.connection_status.setText("❌ Non connecté")
            
            # Reset de l'interface
            if hasattr(self, 'current_items'):
                del self.current_items
            self.content_table.setRowCount(0)
            self.preview_text.clear()
        else:
            self.current_connection = None
    
    # === MÉTHODES UTILITAIRES SUPPLÉMENTAIRES ===
    
    def is_craig_nextcloud_server(self):
        """Détecte si c'est un serveur CRAIG/Nextcloud avec partage public"""
        base_url = self.current_connection.get('url', '').lower()
        return '/s/opendata' in base_url or 'craig.fr' in base_url
        
    def is_nextcloud_shared_link(self):
        """Détecte si l'URL actuelle est un lien de partage Nextcloud"""
        url = self.current_connection.get('url', '').lower()
        return '/s/' in url or '/index.php/s/' in url
        
    def get_nextcloud_share_info(self):
        """Récupère les informations du lien de partage Nextcloud"""
        url = self.current_connection.get('url', '')
        
        # Format : https://domain.com/s/token
        if '/s/' in url:
            base = url.split('/s/')[0]
            token = url.split('/s/')[1].split('/')[0]
            return {
                'base': base,
                'token': token,
                'public_webdav': f"{base}/public.php/webdav",
                'download_base': f"{base}/s/{token}/download"
            }
        
        return None
    
    def build_download_url(self, filename):
        """Construit une URL de téléchargement pour n'importe quel type de serveur WebDAV"""
        try:
            base_url = self.current_connection['url'].rstrip('/')
            
            # Cas 1: Lien de partage Nextcloud
            if self.is_nextcloud_shared_link():
                share_info = self.get_nextcloud_share_info()
                if share_info:
                    # Préparer le chemin relatif
                    path = self.current_path
                    if path == '/':
                        path = ''
                    if path.startswith('/'):
                        path = path[1:]
                    if path and not path.endswith('/'):
                        path += '/'
                    
                    # Construire l'URL de téléchargement direct
                    download_url = f"{share_info['download_base']}?path=/{path}{filename}"
                    print(f"⚡ URL de téléchargement pour lien partagé: {download_url}")
                    return download_url
            
            # Cas 2: Format spécifique CRAIG et liens de partage Nextcloud
            if '/s/opendata' in base_url or '/s/' in base_url:
                # Extraire le chemin dossier (sans le fichier)
                folder_path = self.current_path if self.current_path != '/' else ''
                
                # Débogage complet du chemin CRAIG
                self.debug_craig_path(folder_path, filename)
                
                # Utiliser notre nouvelle fonction spécialisée qui génère exactement le format attendu
                craig_url = self.build_craig_download_url_v2(folder_path, filename)
                if craig_url:
                    return craig_url
                    
                # Si la fonction spéciale échoue pour une raison quelconque, fallback à l'ancienne méthode
                download_url = f"{base_url}/download?path=/{quote(folder_path)}&files={filename}"
                print(f"⚡ URL de téléchargement CRAIG (fallback): {download_url}")
                return download_url
            
            # Cas 3: Standard WebDAV/HTTP
            if self.current_path == '/':
                return f"{base_url}/{filename}"
            else:
                path = self.current_path
                if not path.endswith('/'):
                    path += '/'
                return f"{base_url}{path}{filename}"
                
        except Exception as e:
            print(f"Erreur construction URL de téléchargement: {e}")
            # Fallback vers URL standard
            return urljoin(self.current_connection['url'] + self.current_path, filename)
    
    # Alias pour la compatibilité rétrocompatible
    def build_craig_download_url(self, filename):
        """Alias pour build_download_url pour compatibilité"""
        return self.build_download_url(filename)
    
    def examine_archive(self, archive_data):
        """Examine le contenu d'une archive"""
        try:
            # Nettoyer l'URL de l'archive
            raw_url = archive_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Debug
            print(f"⚡ Examen de l'archive: {clean_url}")
            self.status_label.setText(f"📦 Examen de l'archive: {clean_url}")
            
            QMessageBox.information(self, "Archive", 
                                  f"Examen d'archives en développement.\n\n"
                                  f"📦 {archive_data['name']}\n"
                                  f"🏷️ Type: {archive_data['file_type']}\n"
                                  f"🔗 URL: {clean_url}")
                                  
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'examiner l'archive:\n{str(e)}")
            self.status_label.setText(f"❌ Erreur: {str(e)}")
    
    def read_metadata(self, metadata_data):
        """Lit un fichier de métadonnées"""
        try:
            # Nettoyer l'URL et télécharger le contenu
            raw_url = metadata_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Debug
            print(f"⚡ Lecture des métadonnées depuis: {clean_url}")
            self.status_label.setText(f"📄 Lecture des métadonnées: {clean_url}")
            
            # Télécharger et afficher le contenu
            response = self.session.get(clean_url, timeout=30)
            
            if response.status_code == 200:
                content = response.text[:5000]  # Limiter à 5000 caractères
                
                dialog = QDialog(self)
                dialog.setWindowTitle(f"Métadonnées - {metadata_data['name']}")
                dialog.resize(600, 400)
                
                layout = QVBoxLayout(dialog)
                
                text_edit = QTextEdit()
                text_edit.setPlainText(content)
                text_edit.setReadOnly(True)
                layout.addWidget(text_edit)
                
                buttons = QDialogButtonBox(QDialogButtonBox.Ok)
                buttons.accepted.connect(dialog.accept)
                layout.addWidget(buttons)
                
                dialog.exec_()
                
            else:
                raise Exception(f"Erreur HTTP {response.status_code} - URL: {clean_url}")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire les métadonnées:\n{str(e)}")
            self.status_label.setText(f"❌ Erreur: {str(e)}")
    
    def refresh_html_content(self):
        """Actualise le contenu HTML (pour partages publics comme CRAIG)"""
        folder_url = self.current_connection['url'].rstrip('/')
        if self.current_path != "/":
            folder_url += self.current_path
        
        response = self.session.get(folder_url, timeout=30)
        
        if response.status_code == 200:
            items = self.parse_html_response(response.text, folder_url)
            self.populate_content_table(items)
            self.update_navigation_ui()
            self.status_label.setText(f"✅ {len(items)} éléments trouvés (HTML)")
        else:
            raise Exception(f"Erreur HTTP {response.status_code}")
    
    def parse_html_response(self, html_content, base_url):
        """Parse le HTML pour extraire les fichiers et dossiers"""
        items = []
        
        try:
            import re
            from urllib.parse import urljoin, unquote
            
            # Pattern pour les liens dans le HTML
            # Recherche les liens href avec différents formats possibles
            link_patterns = [
                r'href=["\']([^"\']*/?)["\'][^>]*(?:title=["\']([^"\']*)["\'])?[^>]*>([^<]*)',
                r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>([^<]*)</a>',
                r'href=["\']([^"\']*)["\']'
            ]
            
            found_links = set()  # Pour éviter les doublons
            
            for pattern in link_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        link_url = match[0]
                        link_text = match[1] if len(match) > 1 else match[0]
                        title = match[2] if len(match) > 2 else ""
                    else:
                        link_url = match
                        link_text = match
                        title = ""
                    
                    # Nettoyer et valider le lien
                    if link_url and not link_url.startswith(('http', 'mailto:', 'javascript:', '#')):
                        # Construire l'URL complète
                        full_url = urljoin(base_url + '/', link_url)
                        
                        # Extraire le nom du fichier/dossier
                        name = unquote(link_url.split('/')[-1]) if link_url.endswith('/') else unquote(link_url.split('/')[-1])
                        
                        if name and name not in ['.', '..', ''] and (name, full_url) not in found_links:
                            found_links.add((name, full_url))
                            
                            # Déterminer si c'est un dossier
                            is_folder = (
                                link_url.endswith('/') or 
                                '.' not in name or
                                any(folder_word in link_text.lower() for folder_word in ['dossier', 'folder', 'directory']) or
                                any(folder_word in title.lower() for folder_word in ['dossier', 'folder', 'directory'])
                            )
                            
                            item = self.create_html_item(name, full_url, is_folder, link_text, title)
                            if item:
                                items.append(item)
            
            # Si peu de liens trouvés, essayer une approche plus agressive
            if len(items) < 3:
                items.extend(self.parse_html_aggressive(html_content, base_url))
            
            # Tri : dossiers d'abord, puis fichiers par nom
            items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
            
        except Exception as e:
            print(f"Erreur parsing HTML: {e}")
            
            # Fallback : créer un item avec info de débogage
            debug_item = {
                'name': '🔍 Contenu HTML détecté (mode debug)',
                'path': base_url,
                'is_folder': False,
                'size': len(html_content),
                'size_formatted': self.format_size(len(html_content)),
                'date': "",
                'content_type': "text/html",
                'extension': '.html',
                'file_type': 'html_debug',
                'icon_type': 'text',
                'handler': lambda x: self.show_html_debug(html_content),
                'description': f"Contenu HTML ({len(html_content)} caractères)",
                'url': base_url
            }
            items.append(debug_item)
        
        return items
    
    def parse_html_aggressive(self, html_content, base_url):
        """Parse HTML plus agressif pour cas difficiles"""
        items = []
        
        try:
            # Recherche de patterns spécifiques CRAIG/Nextcloud
            craig_patterns = [
                # Pattern pour les fichiers avec extensions géographiques
                r'([0-9\-]+\.(?:tif|tiff|shp|gpkg|geojson|kml))',
                # Pattern pour les dossiers d'années
                r'(20[0-9]{2})/?',
                # Pattern pour les noms de zones
                r'([a-z_]+_[0-9]{4}|[a-z]+_[a-z]+)',
                # Pattern générique pour noms de fichiers
                r'([a-zA-Z0-9\-_\.]+\.(?:gpkg|zip|tif|shp|json|xml))'
            ]
            
            found_items = set()
            
            for pattern in craig_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                
                for match in matches:
                    name = match.strip()
                    if name and name not in found_items:
                        found_items.add(name)
                        
                        # Construire l'URL de téléchargement
                        if name.endswith('/'):
                            # Dossier
                            full_url = urljoin(base_url + '/', name)
                            is_folder = True
                        else:
                            # Fichier - construire l'URL selon le type de serveur
                            if self.is_craig_nextcloud_server() and any(ext in name.lower() for ext in ['.tif', '.gpkg', '.zip', '.shp']):
                                # URL de téléchargement direct CRAIG/Nextcloud
                                full_url = self.build_craig_download_url(name)
                            else:
                                # URL standard
                                full_url = urljoin(base_url + '/', name)
                            is_folder = False
                        
                        item = self.create_html_item(name, full_url, is_folder, name, "")
                        if item:
                            items.append(item)
        
        except Exception as e:
            print(f"Erreur parsing HTML agressif: {e}")
        
        return items
    
    def create_html_item(self, name, url, is_folder, display_text="", title=""):
        """Crée un item à partir d'un élément HTML"""
        try:
            # Nettoyer le nom
            clean_name = name.strip()
            if not clean_name:
                return None
            
            # Propriétés de base
            size = 0
            date = ""
            content_type = ""
            
            # Détection du type de fichier
            file_extension = ""
            file_info = None
            description = ""
            
            if not is_folder:
                file_extension = PyPath(clean_name).suffix.lower()
                file_info = self.file_handlers.get(file_extension, {
                    'type': 'unknown', 'icon': 'file', 'handler': self.handle_generic_file
                })
                description = self.get_file_description(file_info['type'], size)
                
                # Pour les fichiers .gpkg, essayer d'estimer la taille depuis le contexte
                if file_extension == '.gpkg' and 'dallage' in clean_name.lower():
                    description = "Base de données géographiques (dalles PCRS)"
                
            else:
                file_info = {'type': 'folder', 'icon': 'folder', 'handler': self.handle_folder}
                description = "Dossier"
                
                # Nettoyer l'URL des dossiers
                if not url.endswith('/'):
                    url += '/'
            
            return {
                'name': clean_name,
                'path': url,  # Pour les éléments HTML, path = URL complète
                'is_folder': is_folder,
                'size': size,
                'size_formatted': self.format_size(size) if not is_folder else "",
                'date': date,
                'content_type': content_type,
                'extension': file_extension,
                'file_type': file_info['type'],
                'icon_type': file_info['icon'],
                'handler': file_info['handler'],
                'description': description,
                'url': url
            }
            
        except Exception as e:
            print(f"Erreur création item HTML: {e}")
            return None
    
    def show_html_debug(self, html_content):
        """Affiche le contenu HTML brut pour débogage"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Contenu HTML brut")
        dialog.resize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        # Afficher un échantillon du HTML
        preview_text = QTextEdit()
        preview_text.setReadOnly(True)
        preview_text.setPlainText(html_content[:10000])  # Premier 10k caractères
        layout.addWidget(preview_text)
        
        # Info
        info_label = QLabel(f"Taille totale: {len(html_content)} caractères")
        layout.addWidget(info_label)
        
        # Boutons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        
        dialog.exec_()
    
    def refresh_geopackage_content(self):
        """Actualise le contenu du GeoPackage actuel"""
        if hasattr(self, 'current_geopackage') and self.current_geopackage:
            # Re-analyser le GeoPackage
            self.explore_geopackage(self.current_geopackage)

    def clean_nextcloud_path(self, path):
        """
        Nettoie les chemins des serveurs NextCloud pour éviter les duplications
        Utile quand le serveur renvoie des chemins contenant déjà l'URL complète
        """
        if not path:
            return '/'
            
        base_url = self.current_connection['url'].rstrip('/')
        
        # Cas 1: Si le chemin commence par l'URL de base, extraire la partie relative
        if path.startswith(base_url):
            relative_path = path[len(base_url):]
            if not relative_path:
                return '/'
            if not relative_path.startswith('/'):
                relative_path = '/' + relative_path
            
            # Vérifier si la partie extraite contient encore des duplications
            return self.clean_nextcloud_path(relative_path)
        
        # Cas 2: Duplication spécifique pour Nextcloud/ownCloud (/remote.php/dav/...) et liens partagés
        nextcloud_patterns = [
            r'(.*/remote\.php/dav/files/[^/]+)/(.*?/)*remote\.php/dav/files/[^/]+/(.*)', 
            r'(.*/index\.php/dav/files/[^/]+)/(.*?/)*index\.php/dav/files/[^/]+/(.*)', 
            r'(.*/owncloud/remote\.php/dav/files/[^/]+)/(.*?/)*owncloud/remote\.php/dav/files/[^/]+/(.*)',
            r'(.*/mdrive/remote\.php/dav/files/[^/]+)/(.*?/)*mdrive/remote\.php/dav/files/[^/]+/(.*)',
            r'(.*/public\.php/webdav)/(.*?/)*public\.php/webdav/(.*)'  # Pour les liens partagés
        ]
        
        for pattern in nextcloud_patterns:
            match = re.match(pattern, path)
            if match:
                # Groupe 1 est la première partie du chemin, groupe 3 est ce qui suit la duplication
                clean_path = match.group(3) if match.group(3) else ''
                if not clean_path.startswith('/'):
                    clean_path = '/' + clean_path
                return clean_path
                
        # Cas 3: Duplication de segments spécifiques
        segments_to_check = ['/remote.php/', '/index.php/', '/mdrive/', '/owncloud/', '/public.php/webdav/']
        for segment in segments_to_check:
            if segment in path:
                parts = path.split(segment)
                if len(parts) > 2:
                    # Si un segment apparaît plus d'une fois
                    reconstructed = segment + parts[-1]  # Prendre seulement la dernière partie
                    return reconstructed if reconstructed.startswith('/') else '/' + reconstructed
        
        # Cas 4: Si c'est un chemin relatif normal
        if not path.startswith('/'):
            return '/' + path
            
        return path
    
    def debug_url_construction(self, method_name, raw_path, clean_path, final_url):
        """Méthode de débogage pour surveiller la construction des URLs"""
        # Construire un message détaillé pour le débogage des chemins
        debug_message = f"""
⚡ DEBUG URL CONSTRUCTION dans {method_name}:
- URL de base: {self.current_connection['url']}
- Chemin actuel: {self.current_path}
- Chemin brut: {raw_path}
- Chemin nettoyé: {clean_path}
- URL finale: {final_url}
"""
        # Afficher dans la console pour débogage
        print(debug_message)
        
        # Ajouter au label de statut pour l'utilisateur
        if not self.status_label.text().startswith("❌"):
            self.status_label.setText(f"📊 {method_name}: {final_url}")
        
        # Vérifier si le motif de duplication est présent
        if '/remote.php/' in final_url:
            count_remote_php = final_url.count('/remote.php/')
            if count_remote_php > 1:
                print(f"⚠️ ALERTE: Duplication détectée ({count_remote_php}x '/remote.php/')")
                
        # Vérifier d'autres cas courants de duplication
        base_parts = []
        if '/index.php/' in self.current_connection['url']:
            base_parts.append('/index.php/')
        if '/mdrive/' in self.current_connection['url']:
            base_parts.append('/mdrive/')
        if '/owncloud/' in self.current_connection['url']:
            base_parts.append('/owncloud/')
            
        for part in base_parts:
            count_part = final_url.count(part)
            if count_part > 1:
                print(f"⚠️ ALERTE: Duplication détectée ({count_part}x '{part}')")
                
        return debug_message
    
    def clean_nextcloud_url(self, raw_url):
        """
        Nettoie une URL NextCloud/mdrive pour éliminer les duplications de chemins.
        Cette fonction est utilisée pour tous les accès aux fichiers (chargement, téléchargement, etc.)
        """
        if not raw_url or not raw_url.startswith('http'):
            return raw_url
            
        # Cas spécifiques pour les formats observés dans les erreurs
        specific_patterns = [
            # Pattern pour mdrive
            r'(https?://[^/]+/mdrive/remote\.php/dav/files/[^/]+)/mdrive/remote\.php/dav/files/[^/]+/(.+)',
            # Pattern pour les liens partagés avec public.php/webdav
            r'(https?://[^/]+/public\.php/webdav)/public\.php/webdav/(.+)'
        ]
        
        for pattern in specific_patterns:
            match = re.match(pattern, raw_url)
            if match:
                base_part = match.group(1)  # première partie de l'URL
                file_part = match.group(2)  # chemin du fichier après la duplication
                clean_url = f"{base_part}/{file_part}"
                print(f"⚡ URL nettoyée (cas spécifique):\nAvant: {raw_url}\nAprès: {clean_url}")
                return clean_url
        
        # Cas général avec détection plus robuste des duplications
        base_url = self.current_connection['url'].rstrip('/')
        
        # Identifier les segments problématiques à surveiller
        server_part = re.match(r'(https?://[^/]+)', base_url)
        if server_part:
            server = server_part.group(1)
        else:
            server = ""
            
        # Cas pour les URLs qui ont une structure NextCloud/ownCloud typique
        nextcloud_patterns = [
            # Format: serveur/segment/user/segment/user/path
            r'(https?://[^/]+/[^/]+/remote\.php/dav/files/[^/]+)/(?:[^/]+/)*remote\.php/dav/files/[^/]+/(.+)',
            r'(https?://[^/]+/[^/]+/index\.php/dav/files/[^/]+)/(?:[^/]+/)*index\.php/dav/files/[^/]+/(.+)',
            # Duplication simple du chemin complet
            r'(https?://[^/]+/[^/]+/[^/]+/[^/]+/[^/]+)/\1/(.+)'
        ]
        
        for pattern in nextcloud_patterns:
            match = re.match(pattern, raw_url)
            if match:
                base_part = match.group(1)  # première partie de l'URL
                file_part = match.group(2)  # chemin du fichier après la duplication
                clean_url = f"{base_part}/{file_part}"
                print(f"⚡ URL nettoyée (pattern standard):\nAvant: {raw_url}\nAprès: {clean_url}")
                return clean_url
        
        # Si aucun des patterns ne correspond mais qu'il semble y avoir une duplication
        # Approche par segments
        segments_to_check = ['/remote.php/', '/index.php/', '/mdrive/', '/owncloud/', '/public.php/webdav/']
        for segment in segments_to_check:
            if segment in raw_url and raw_url.count(segment) > 1:
                # Diviser par le segment et reconstruire en prenant seulement la première occurrence
                parts = raw_url.split(segment)
                if len(parts) > 2:
                    # Il y a au moins une duplication
                    prefix = parts[0] + segment
                    # Trouver le chemin significatif après la dernière occurrence
                    path_part = parts[-1]
                    
                    # Si le chemin ne commence pas après un segment, mais après un sous-chemin
                    if '/' in path_part:
                        path_components = path_part.split('/')
                        # Chercher le premier composant qui ressemble à un nom de fichier ou dossier réel
                        # (pas un composant d'URL NextCloud)
                        for i, comp in enumerate(path_components):
                            if comp and comp not in ['remote.php', 'dav', 'files', 'mdrive', 'index.php']:
                                # Reconstruire le chemin à partir de ce composant
                                real_path = '/'.join(path_components[i:])
                                clean_url = f"{prefix}{real_path}"
                                print(f"⚡ URL nettoyée (segmentation):\nAvant: {raw_url}\nAprès: {clean_url}")
                                return clean_url
        
        # Si aucune duplication n'est détectée ou si nous ne savons pas comment la gérer
        return raw_url
    
    def load_shapefile_with_dependencies(self, file_data):
        """
        Méthode spéciale pour les shapefiles - télécharge tous les fichiers annexes nécessaires
        puis charge le shapefile dans QGIS à partir du stockage local temporaire
        """
        try:
            # Importer tous les modules nécessaires au début de la fonction
            import os, tempfile, shutil
            
            shapefile_name = file_data['name']
            base_name = shapefile_name[:-4]  # Enlever l'extension .shp
            
            # Extraire correctement l'URL du dossier parent
            parent_url = os.path.dirname(file_data['url'])
            clean_parent_url = self.clean_nextcloud_url(parent_url)
            
            # Informations pour le débogage
            self.status_label.setText(f"🔍 Analyse du shapefile {shapefile_name}")
            print(f"⚡ Analyse du shapefile: {shapefile_name}")
            print(f"⚡ URL parent: {clean_parent_url}")
            print(f"⚡ Nom de base: {base_name}")
            
            # Créer un dossier temporaire pour stocker les fichiers
            temp_dir = tempfile.mkdtemp(prefix="qgis_webdav_")
            print(f"⚡ Dossier temporaire créé: {temp_dir}")
            
            # Les extensions des fichiers annexes d'un shapefile, par ordre d'importance
            shapefile_exts = ['.shp', '.shx', '.dbf', '.prj', '.qpj', '.cpg', '.sbn', '.sbx', '.xml']
            # Extensions essentielles qui doivent être présentes
            essential_exts = ['.shp', '.shx', '.dbf'] 
            
            # Télécharger tous les fichiers possibles
            downloaded_files = []
            download_success = True
            essential_files_found = {ext: False for ext in essential_exts}
            
            # Informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            
            # Créer une session avec authentification
            import requests
            session = requests.Session()
            if username and password:
                session.auth = (username, password)
                
            # Définir l'en-tête User-Agent
            session.headers.update({
                'User-Agent': 'QGIS-WebDAV-Explorer/1.0'
            })
            
            # Méthode alternative pour trouver les fichiers disponibles dans le dossier
            try:
                # Essayer de lister le contenu du dossier parent avec WebDAV
                self.status_label.setText(f"🔍 Recherche des fichiers associés...")
                folder_response = session.request('PROPFIND', clean_parent_url, 
                                              headers={'Depth': '1'}, 
                                              timeout=30)
                
                if folder_response.status_code == 207:  # Multi-Status
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(folder_response.text)
                    
                    # Liste des fichiers trouvés avec leur extension
                    folder_files = {}
                    
                    for response in root.findall('.//{DAV:}response'):
                        href = response.find('.//{DAV:}href')
                        if href is not None:
                            file_path = href.text
                            file_name = os.path.basename(file_path.rstrip('/'))
                            
                            # Si le fichier commence par le même nom de base
                            if file_name.startswith(base_name):
                                _, ext = os.path.splitext(file_name)
                                ext = ext.lower()
                                if ext:
                                    folder_files[ext] = file_path
                                    print(f"⚡ Fichier trouvé dans le dossier: {file_name} ({ext})")
                    
                    # Vérifier si les fichiers essentiels sont disponibles
                    for ext in essential_exts:
                        if ext in folder_files:
                            print(f"✅ Fichier essentiel trouvé: {base_name}{ext}")
                        else:
                            print(f"❌ Fichier essentiel manquant dans le dossier: {base_name}{ext}")
                            
                    # On peut utiliser cette information pour construire des URLs plus précises
                    if folder_files:
                        print(f"⚡ {len(folder_files)} fichiers associés trouvés dans le dossier")
            except Exception as e:
                print(f"⚠️ Erreur lors de la recherche des fichiers dans le dossier: {str(e)}")
            
            # Essayer les deux méthodes de construction d'URL pour les fichiers
            url_methods = [
                # Méthode 1: URL du dossier parent + nom du fichier
                lambda ext: f"{clean_parent_url}/{base_name}{ext}",
                # Méthode 2: Remplacer l'extension dans l'URL d'origine
                lambda ext: file_data['url'].replace('.shp', ext)
            ]
            
            for ext in shapefile_exts:
                # Essayer chaque méthode de construction d'URL jusqu'à ce qu'une fonctionne
                for url_method in url_methods:
                    try:
                        file_url = url_method(ext)
                        file_name = f"{base_name}{ext}"
                        
                        self.status_label.setText(f"🔄 Téléchargement de {file_name}...")
                        print(f"⚡ Tentative de téléchargement: {file_url}")
                        
                        # Télécharger le fichier
                        response = session.get(file_url, stream=True, timeout=30)
                        
                        if response.status_code == 200:
                            # Sauvegarder le fichier dans le dossier temporaire
                            temp_file_path = os.path.join(temp_dir, file_name)
                            with open(temp_file_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            
                            downloaded_files.append(temp_file_path)
                            print(f"✅ Téléchargé: {file_name}")
                            
                            # Marquer si un fichier essentiel a été trouvé
                            if ext in essential_exts:
                                essential_files_found[ext] = True
                                
                            # Si on a réussi avec cette méthode, pas besoin d'essayer l'autre
                            break
                        else:
                            print(f"⚠️ Erreur HTTP {response.status_code} pour {file_name} avec la méthode {url_methods.index(url_method) + 1}")
                    
                    except Exception as e:
                        print(f"⚠️ Erreur avec la méthode {url_methods.index(url_method) + 1} pour {file_name}: {str(e)}")
            
            # Si après avoir essayé les deux méthodes, on n'a toujours pas tous les fichiers essentiels,
            # essayons une approche directe avec l'URL du shapefile
            if not all(essential_files_found.values()):
                try:
                    # Télécharger d'abord le .shp directement depuis son URL d'origine
                    self.status_label.setText(f"🔄 Téléchargement direct de {shapefile_name}...")
                    response = session.get(file_data['url'], stream=True, timeout=30)
                    
                    if response.status_code == 200:
                        # Sauvegarder le fichier .shp
                        shp_path = os.path.join(temp_dir, shapefile_name)
                        with open(shp_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        
                        essential_files_found['.shp'] = True
                        print(f"✅ Téléchargement direct réussi: {shapefile_name}")
                        
                        # Pour .shx et .dbf, essayer de remplacer directement l'extension dans l'URL
                        for ext in ['.shx', '.dbf']:
                            if not essential_files_found[ext]:
                                direct_url = file_data['url'].replace('.shp', ext)
                                print(f"⚡ Tentative directe pour {ext}: {direct_url}")
                                
                                response = session.get(direct_url, stream=True, timeout=30)
                                if response.status_code == 200:
                                    file_path = os.path.join(temp_dir, base_name + ext)
                                    with open(file_path, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            if chunk:
                                                f.write(chunk)
                                    essential_files_found[ext] = True
                                    print(f"✅ Téléchargement direct réussi: {base_name}{ext}")
                except Exception as e:
                    print(f"⚠️ Erreur lors du téléchargement direct: {str(e)}")
            
            # Vérification finale des fichiers disponibles dans le dossier temporaire
            print(f"⚡ Fichiers téléchargés dans {temp_dir}:")
            for f in os.listdir(temp_dir):
                print(f"   - {f}")
                
            # Vérifier si tous les fichiers essentiels sont présents
            missing_exts = []
            for ext, found in essential_files_found.items():
                if not found:
                    missing_exts.append(ext)
            
            # Si des fichiers essentiels sont manquants
            if missing_exts:
                error_msg = f"Impossible de télécharger tous les fichiers nécessaires. Manquant: {', '.join(missing_exts)}"
                print(f"❌ {error_msg}")
                raise Exception(error_msg)
            
            # Si le téléchargement a réussi pour les fichiers essentiels
            if all(essential_files_found.values()):
                # Trouver le fichier .shp
                shp_file = next((f for f in os.listdir(temp_dir) if f.endswith('.shp')), None)
                
                if shp_file:
                    # Construire le chemin complet
                    shp_path = os.path.join(temp_dir, shp_file)
                    
                    # Charger le shapefile dans QGIS
                    self.status_label.setText(f"🔄 Chargement du shapefile local: {shp_file}")
                    layer = QgsVectorLayer(shp_path, base_name, "ogr")
                    
                    if layer.isValid():
                        # Ajouter au projet QGIS
                        QgsProject.instance().addMapLayer(layer)
                        self.status_label.setText(f"✅ Shapefile chargé: {base_name}")
                        
                        # Gestion des fichiers temporaires - les garder jusqu'à la fermeture de QGIS
                        # ou créer un gestionnaire de fichiers temporaires plus sophistiqué
                        # Pour l'instant, on les garde (nécessaire pour que QGIS puisse y accéder)
                        print(f"✅ Shapefile chargé avec succès depuis: {shp_path}")
                        
                        QMessageBox.information(self, "Succès", 
                                               f"Shapefile chargé avec succès!\n\n"
                                               f"📄 {base_name}")
                        return True
                    else:
                        error_msg = layer.error().message() if hasattr(layer, 'error') and layer.error() else "Couche invalide"
                        # Afficher plus d'informations de débogage
                        print(f"⚠️ Fichiers téléchargés dans: {temp_dir}")
                        print(f"⚠️ Fichiers disponibles: {os.listdir(temp_dir)}")
                        print(f"⚠️ Erreur du chargement de couche: {error_msg}")
                        raise Exception(f"Shapefile invalide: {error_msg}")
                else:
                    raise Exception("Fichier .shp non trouvé après téléchargement")
            else:
                # Nettoyage en cas d'échec
                missing_files = [ext for ext, found in essential_files_found.items() if not found]
                raise Exception(f"Impossible de télécharger tous les fichiers nécessaires. Manquant: {', '.join(missing_files)}")
        
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Erreur lors du chargement du shapefile: {error_msg}")
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le shapefile:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def upload_file_to_webdav(self):
        """Téléverse un fichier local vers le serveur WebDAV"""
        if not self.session or not self.current_connection:
            QMessageBox.warning(self, "Erreur", "Vous devez d'abord vous connecter à un serveur WebDAV")
            return
            
        try:
            # Demander le fichier à téléverser
            file_paths, _ = QFileDialog.getOpenFileNames(
                self, "Sélectionner les fichiers à téléverser", 
                "",  # Dossier de départ
                "Tous les fichiers (*)"
            )
            
            if not file_paths:
                return
                
            # Vérifier le dossier de destination (dossier courant)
            destination_path = self.current_path
            
            # Confirmation
            if len(file_paths) == 1:
                msg = f"Téléverser le fichier :\n{os.path.basename(file_paths[0])}\n\nVers le dossier :\n{destination_path}"
            else:
                msg = f"Téléverser {len(file_paths)} fichiers vers le dossier :\n{destination_path}"
                
            reply = QMessageBox.question(self, "Confirmer le téléversement", msg, 
                                       QMessageBox.Yes | QMessageBox.No)
                                       
            if reply != QMessageBox.Yes:
                return
                
            # Configurer la barre de progression
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, len(file_paths))
            self.progress_bar.setValue(0)
            
            # Téléverser chaque fichier
            success_count = 0
            base_url = self.current_connection['url'].rstrip('/')
            
            # Informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            
            for i, local_path in enumerate(file_paths):
                try:
                    filename = os.path.basename(local_path)
                    self.status_label.setText(f"🔄 Téléversement de {filename}...")
                    
                    # Construire l'URL de destination
                    if destination_path == '/':
                        dest_url = f"{base_url}/{filename}"
                    else:
                        dest_url = f"{base_url}{destination_path}{filename}"
                        
                    print(f"⚡ Téléversement vers: {dest_url}")
                    
                    # Lire le fichier local
                    with open(local_path, 'rb') as f:
                        file_content = f.read()
                    
                    # Téléverser avec PUT
                    response = self.session.put(dest_url, data=file_content)
                    
                    if response.status_code in [200, 201, 204]:
                        success_count += 1
                        print(f"✅ Téléversement réussi: {filename}")
                    else:
                        print(f"❌ Échec du téléversement: {filename} (HTTP {response.status_code})")
                        
                except Exception as e:
                    print(f"❌ Erreur lors du téléversement de {filename}: {str(e)}")
                    
                # Mettre à jour la progression
                self.progress_bar.setValue(i + 1)
                QApplication.processEvents()
            
            # Rafraîchir le contenu après le téléversement
            self.refresh_current_location()
            
            # Résumé
            if success_count == len(file_paths):
                self.status_label.setText(f"✅ Téléversement terminé: {success_count} fichiers")
                QMessageBox.information(self, "Téléversement terminé", 
                                      f"Tous les fichiers ont été téléversés avec succès.")
            else:
                self.status_label.setText(f"⚠️ Téléversement partiel: {success_count}/{len(file_paths)} fichiers")
                QMessageBox.warning(self, "Téléversement partiel", 
                                  f"{success_count} fichiers sur {len(file_paths)} ont été téléversés.")
        
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Erreur lors du téléversement:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            
        finally:
            self.progress_bar.setVisible(False)
    
    def create_folder_on_webdav(self):
        """Crée un nouveau dossier sur le serveur WebDAV"""
        if not self.session or not self.current_connection:
            QMessageBox.warning(self, "Erreur", "Vous devez d'abord vous connecter à un serveur WebDAV")
            return
            
        try:
            # Demander le nom du dossier
            folder_name, ok = QInputDialog.getText(self, "Nouveau dossier", 
                                                 "Nom du dossier:")
            
            if not ok or not folder_name:
                return
                
            # Vérifier que le nom est valide (pas de caractères spéciaux)
            import re
            if not re.match(r'^[a-zA-Z0-9_\-. ]+$', folder_name):
                QMessageBox.warning(self, "Nom invalide", 
                                  "Le nom du dossier contient des caractères non autorisés.\n"
                                  "Utilisez uniquement des lettres, chiffres, espaces, tirets, points et underscores.")
                return
                
            # Construire l'URL
            base_url = self.current_connection['url'].rstrip('/')
            if self.current_path == '/':
                folder_url = f"{base_url}/{folder_name}"
            else:
                folder_url = f"{base_url}{self.current_path}{folder_name}"
                
            # Créer le dossier avec MKCOL
            self.status_label.setText(f"🔄 Création du dossier: {folder_name}...")
            print(f"⚡ Création du dossier: {folder_url}")
            
            response = self.session.request('MKCOL', folder_url)
            
            if response.status_code in [201, 200, 204]:
                self.status_label.setText(f"✅ Dossier créé: {folder_name}")
                print(f"✅ Dossier créé avec succès: {folder_url}")
                
                # Rafraîchir le contenu
                self.refresh_current_location()
            else:
                error_msg = f"Erreur HTTP {response.status_code}"
                raise Exception(error_msg)
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
    
    def load_all_geopackage_layers(self, gpkg_path, name):
        """Charge toutes les couches disponibles dans un GeoPackage"""
        try:
            # Importer les modules nécessaires
            import os, sqlite3
            
            self.status_label.setText("🔄 Chargement des couches du GeoPackage...")
            
            # Explorer la structure du GeoPackage avec SQLite
            conn = sqlite3.connect(gpkg_path)
            cursor = conn.cursor()
            
            try:
                # Lister les couches disponibles
                cursor.execute("SELECT table_name, data_type FROM gpkg_contents")
                layers = cursor.fetchall()
                
                if not layers:
                    raise Exception("Aucune couche trouvée dans le GeoPackage")
                
                # Créer un groupe pour les couches
                root = QgsProject.instance().layerTreeRoot()
                group_name = f"GeoPackage - {name}"
                group = root.findGroup(group_name)
                if group is None:
                    group = root.insertGroup(0, group_name)
                
                # Charger chaque couche
                loaded_layers = 0
                
                for layer_name, data_type in layers:
                    self.status_label.setText(f"🔄 Chargement de {layer_name}...")
                    
                    # Déterminer le type de couche
                    if data_type == 'features':
                        # Couche vecteur
                        layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")
                    elif data_type == 'tiles':
                        # Couche raster
                        layer = QgsRasterLayer(f"{gpkg_path}|layername={layer_name}", layer_name)
                    else:
                        # Type inconnu, essayer en vecteur par défaut
                        layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")
                        
                        # Si ça ne marche pas, essayer en raster
                        if not layer.isValid():
                            layer = QgsRasterLayer(f"{gpkg_path}|layername={layer_name}", layer_name)
                    
                    if layer.isValid():
                        # Ajouter au groupe
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)
                        loaded_layers += 1
                    else:
                        print(f"⚠️ Couche non valide: {layer_name}")
                
                self.status_label.setText(f"✅ GeoPackage: {loaded_layers}/{len(layers)} couches chargées")
                
                # Informer l'utilisateur
                if loaded_layers > 0:
                    QMessageBox.information(self, "Succès", 
                                          f"GeoPackage chargé avec succès!\n\n"
                                          f"📄 {name}\n"
                                          f"🏷️ {loaded_layers} couche(s) chargée(s)")
                    return True
                else:
                    raise Exception("Aucune couche n'a pu être chargée")
                    
            except Exception as e:
                raise Exception(f"Erreur lors du chargement des couches: {str(e)}")
            finally:
                conn.close()
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le GeoPackage:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def load_csv_excel_file(self, file_data):
        """
        Charge un fichier CSV ou Excel comme couche de données
        Simule l'import CSV/délimité standard de QGIS
        """
        try:
            # Importer les modules nécessaires
            import os, tempfile
            
            self.status_label.setText(f"🔄 Préparation du fichier {file_data['name']}...")
            
            # Nettoyer l'URL
            raw_url = file_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Déterminer le type de fichier
            file_extension = os.path.splitext(file_data['name'].lower())[1]
            is_excel = file_extension in ['.xlsx', '.xls']
            is_csv = file_extension == '.csv'
            
            # Informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            
            # Créer une session avec authentification
            import requests
            session = requests.Session()
            if username and password:
                session.auth = (username, password)
                
            # Définir l'en-tête User-Agent
            session.headers.update({
                'User-Agent': 'QGIS-WebDAV-Explorer/1.0'
            })
            
            # Télécharger le fichier
            self.status_label.setText(f"🔄 Téléchargement de {file_data['name']}...")
            response = session.get(clean_url, stream=True, timeout=30)
            
            if response.status_code != 200:
                raise Exception(f"Erreur téléchargement: {response.status_code}")
            
            # Sauvegarder temporairement
            with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                local_file = tmp_file.name
            
            # Pour les fichiers Excel, convertir en CSV si nécessaire
            if is_excel:
                try:
                    # Vérifier si pandas est disponible
                    import pandas as pd
                    
                    # Convertir Excel en CSV
                    self.status_label.setText(f"🔄 Conversion Excel vers CSV...")
                    df = pd.read_excel(local_file)
                    
                    # Sauvegarder comme CSV
                    csv_file = local_file + '.csv'
                    df.to_csv(csv_file, index=False)
                    
                    # Utiliser ce fichier CSV pour la suite
                    local_file = csv_file
                    is_csv = True
                    
                except ImportError:
                    # Si pandas n'est pas disponible
                    QMessageBox.warning(self, "Module manquant", 
                                      "Le module pandas est nécessaire pour traiter les fichiers Excel.\n"
                                      "Installation recommandée: pip install pandas openpyxl")
                    raise Exception("pandas non disponible pour traiter le fichier Excel")
            
            # Ouvrir le dialogue d'import de délimité de QGIS
            if is_csv:
                self.status_label.setText(f"🔄 Ouverture du fichier délimité...")
                
                # Créer un dialogue d'import de texte délimité
                from qgis.core import QgsVectorLayer
                
                # 1. Détection automatique du délimiteur et de l'encodage
                layer = QgsVectorLayer(local_file, os.path.basename(file_data['name']), "delimitedtext")
                
                if not layer.isValid():
                    # 2. Essai avec délimiteur explicite
                    uri = f"file:///{local_file}?delimiter=,&detectTypes=yes&geomType=none"
                    layer = QgsVectorLayer(uri, os.path.basename(file_data['name']), "delimitedtext")
                    
                    if not layer.isValid():
                        # 3. Essai avec délimiteur point-virgule (format européen)
                        uri = f"file:///{local_file}?delimiter=;&detectTypes=yes&geomType=none"
                        layer = QgsVectorLayer(uri, os.path.basename(file_data['name']), "delimitedtext")
                
                if layer.isValid():
                    # Ajouter la couche à QGIS
                    QgsProject.instance().addMapLayer(layer)
                    self.status_label.setText(f"✅ Fichier délimité chargé: {file_data['name']}")
                    
                    QMessageBox.information(self, "Succès", 
                                          f"Fichier délimité chargé avec succès!\n\n"
                                          f"📄 {file_data['name']}")
                    return True
                else:
                    # Utiliser le dialogue standard de QGIS pour l'import
                    from qgis.gui import QgsDelimitedTextSourceSelect
                    
                    # Créer et afficher le dialogue
                    dlg = QgsDelimitedTextSourceSelect()
                    dlg.setModal(True)
                    
                    # Définir le fichier source
                    dlg.setSourceFile(local_file)
                    
                    # Exécuter le dialogue
                    if dlg.exec_():
                        # La couche a été chargée avec succès via le dialogue
                        self.status_label.setText(f"✅ Fichier délimité chargé: {file_data['name']}")
                        return True
                    else:
                        raise Exception("Import annulé par l'utilisateur")
            
            raise Exception("Format de fichier non pris en charge")
            
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le fichier:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def load_python_script(self, file_data):
        """
        Charge un script Python du WebDAV vers la console Python de QGIS
        """
        try:
            # Importer les modules nécessaires
            import os, tempfile
            
            self.status_label.setText(f"🔄 Chargement du script Python {file_data['name']}...")
            
            # Nettoyer l'URL
            raw_url = file_data['url']
            clean_url = self.clean_nextcloud_url(raw_url)
            
            # Informations d'authentification
            username = self.current_connection.get('username', '')
            password = self.current_connection.get('password', '')
            
            # Créer une session avec authentification
            import requests
            session = requests.Session()
            if username and password:
                session.auth = (username, password)
                
            # Définir l'en-tête User-Agent
            session.headers.update({
                'User-Agent': 'QGIS-WebDAV-Explorer/1.0'
            })
            
            # Télécharger le contenu du script
            response = session.get(clean_url, timeout=30)
            
            if response.status_code != 200:
                raise Exception(f"Erreur téléchargement: {response.status_code}")
            
            # Obtenir le contenu du script
            script_content = response.text
            
            # Essayer d'obtenir la console Python de QGIS
            from qgis.utils import iface
            
            # Chercher d'abord si la console Python est déjà ouverte
            python_console = None
            
            # Méthode 1: Chercher via les dock widgets
            for dock in iface.mainWindow().findChildren(QDockWidget):
                if 'python' in dock.objectName().lower() and 'console' in dock.objectName().lower():
                    python_console = dock
                    break
            
            # Méthode 2: Si la console n'est pas trouvée, essayer de l'ouvrir
            if not python_console:
                # Essayer de trouver l'action pour ouvrir la console
                for action in iface.mainWindow().findChildren(QAction):
                    if 'python' in action.objectName().lower() and 'console' in action.objectName().lower():
                        action.trigger()  # Déclencher l'action pour ouvrir la console
                        break
                
                # Attendre un peu et chercher à nouveau
                import time
                time.sleep(0.5)
                
                # Chercher à nouveau la console
                for dock in iface.mainWindow().findChildren(QDockWidget):
                    if 'python' in dock.objectName().lower() and 'console' in dock.objectName().lower():
                        python_console = dock
                        break
            
            # Si la console est trouvée, essayer d'y insérer le code
            if python_console:
                # Chercher le widget d'édition dans la console
                from qgis.PyQt.QtWidgets import QTextEdit, QPlainTextEdit
                
                # Trouver le widget d'édition de la console
                console_widget = None
                
                for widget in python_console.findChildren(QTextEdit) + python_console.findChildren(QPlainTextEdit):
                    if widget.isEnabled() and widget.isVisible():
                        console_widget = widget
                        break
                
                if console_widget:
                    # Trois options :
                    # 1. Insérer le code (pour référence)
                    # 2. Charger et exécuter le code
                    # 3. Ouvrir dans un éditeur
                    
                    # Demander à l'utilisateur ce qu'il veut faire
                    options = [
                        "Insérer le code dans la console (pour référence)",
                        "Exécuter le script directement",
                        "Ouvrir dans un nouvel éditeur"
                    ]
                    
                    choice, ok = QInputDialog.getItem(self, "Chargement de script Python",
                                                   "Que voulez-vous faire avec ce script?",
                                                   options, 0, False)
                    
                    if ok:
                        if choice == options[0]:  # Insérer le code
                            # Préparer le code avec un commentaire
                            formatted_code = f"# Script chargé depuis WebDAV: {file_data['name']}\n"
                            formatted_code += script_content
                            
                            # Insérer le code dans la console
                            if isinstance(console_widget, QTextEdit):
                                console_widget.insertPlainText(formatted_code)
                            else:
                                console_widget.insertPlainText(formatted_code)
                                
                            self.status_label.setText(f"✅ Script inséré dans la console: {file_data['name']}")
                            return True
                            
                        elif choice == options[1]:  # Exécuter le script
                            # Sauvegarder temporairement
                            with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as tmp_file:
                                tmp_file.write(script_content.encode('utf-8'))
                                script_path = tmp_file.name
                            
                            # Exécuter le script
                            self.status_label.setText(f"🔄 Exécution du script: {file_data['name']}")
                            
                            # Utiliser exec() pour exécuter le script
                            try:
                                # Informer l'utilisateur dans la console
                                if isinstance(console_widget, QTextEdit):
                                    console_widget.insertPlainText(f"\n# Exécution du script WebDAV: {file_data['name']}\n")
                                else:
                                    console_widget.insertPlainText(f"\n# Exécution du script WebDAV: {file_data['name']}\n")
                                
                                # Exécuter le script dans la console
                                # Note: nous utilisons exec() avec précaution car le script vient du WebDAV de l'utilisateur
                                exec(open(script_path, 'r', encoding='utf-8').read())
                                
                                self.status_label.setText(f"✅ Script exécuté: {file_data['name']}")
                                return True
                                
                            except Exception as exec_error:
                                error_msg = str(exec_error)
                                
                                # Afficher l'erreur dans la console
                                if isinstance(console_widget, QTextEdit):
                                    console_widget.insertPlainText(f"\n# Erreur dans l'exécution du script:\n{error_msg}\n")
                                else:
                                    console_widget.insertPlainText(f"\n# Erreur dans l'exécution du script:\n{error_msg}\n")
                                    
                                raise Exception(f"Erreur d'exécution: {error_msg}")
                            
                        elif choice == options[2]:  # Ouvrir dans un éditeur
                            # Sauvegarder temporairement
                            with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as tmp_file:
                                tmp_file.write(script_content.encode('utf-8'))
                                script_path = tmp_file.name
                            
                            # Essayer d'ouvrir l'éditeur de script QGIS
                            try:
                                # Chercher l'éditeur de script
                                from plugins import scripteditor
                                scripteditor.instance.openFile(script_path)
                                
                                self.status_label.setText(f"✅ Script ouvert dans l'éditeur: {file_data['name']}")
                                return True
                                
                            except ImportError:
                                # Si l'éditeur de script n'est pas disponible, ouvrir avec le système
                                import webbrowser
                                webbrowser.open(script_path)
                                
                                self.status_label.setText(f"✅ Script ouvert dans l'éditeur système: {file_data['name']}")
                                return True
                    else:
                        return False  # L'utilisateur a annulé
                        
                else:
                    raise Exception("Impossible de trouver le widget d'édition dans la console Python")
            else:
                # Si la console n'est pas disponible, sauvegarder le script et l'ouvrir directement
                with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as tmp_file:
                    tmp_file.write(script_content.encode('utf-8'))
                    script_path = tmp_file.name
                
                # Ouvrir avec le système
                import webbrowser
                webbrowser.open(script_path)
                
                self.status_label.setText(f"✅ Script sauvegardé et ouvert: {file_data['name']}")
                return True
                
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le script Python:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def save_current_layer_to_webdav(self):
        """Enregistre la couche actuellement sélectionnée sur le serveur WebDAV"""
        try:
            # Importer les modules nécessaires
            import os, tempfile
            
            # Vérifier si une connexion est active
            if not self.current_connection or not hasattr(self, 'current_path'):
                QMessageBox.warning(self, "Erreur", "Aucune connexion WebDAV active")
                return False
            
            # Obtenir la couche active via self.iface
            active_layer = self.iface.activeLayer()
            if not active_layer:
                QMessageBox.warning(self, "Erreur", "Aucune couche active")
                return False
            
            # Déterminer le format de sortie en fonction du type de couche
            if active_layer.type() == QgsMapLayer.VectorLayer:
                # Options pour les couches vectorielles
                formats = [
                    "GeoPackage (*.gpkg)",
                    "Shapefile (*.shp)",
                    "GeoJSON (*.geojson)",
                    "KML (*.kml)",
                    "CSV (*.csv)"
                ]
            elif active_layer.type() == QgsMapLayer.RasterLayer:
                # Options pour les couches raster
                formats = [
                    "GeoTIFF (*.tif)",
                    "JPEG (*.jpg)",
                    "PNG (*.png)"
                ]
            else:
                # Autres types de couches
                formats = [
                    "GeoPackage (*.gpkg)",
                    "Shapefile (*.shp)",
                    "GeoJSON (*.geojson)"
                ]
            
            # Demander le format et le nom de fichier
            format_choice, ok = QInputDialog.getItem(self, "Format d'export", 
                                                "Sélectionner un format:", formats, 0, False)
            if not ok:
                return False
            
            # Extraire l'extension du format choisi
            extension = format_choice.split("*")[1].strip(")").strip()
            
            # Demander le nom de fichier
            suggested_name = active_layer.name().replace(" ", "_") + extension
            file_name, ok = QInputDialog.getText(self, "Nom du fichier", 
                                              "Nom du fichier:", QLineEdit.Normal, 
                                              suggested_name)
            if not ok or not file_name:
                return False
            
            # Ajouter l'extension si elle n'est pas présente
            if not file_name.endswith(extension):
                file_name += extension
            
            # Créer un fichier temporaire
            temp_dir = tempfile.mkdtemp(prefix="qgis_webdav_export_")
            temp_path = os.path.join(temp_dir, file_name)
            
            self.status_label.setText(f"🔄 Préparation de l'export pour {file_name}...")
            
            # Exporter la couche dans le format choisi
            if extension == '.gpkg':
                # Export GeoPackage - compatible avec QGIS 3.4+
                layer_name = active_layer.name()
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    active_layer,
                    temp_path,
                    "utf-8",
                    active_layer.crs(),
                    "GPKG",
                    layerName=layer_name
                )
                
                # Gestion des erreurs compatible avec QGIS 3.4 et 3.10+
                if isinstance(error, tuple):
                    # QGIS 3.10+
                    if error[0] != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error[1]}")
                else:
                    # QGIS 3.4
                    if error != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error}")
                    
            elif extension == '.shp':
                # Export Shapefile (nécessite de gérer les fichiers multiples)
                # Version compatible avec QGIS 3.4
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    active_layer,
                    temp_path,
                    "utf-8",
                    active_layer.crs(),
                    "ESRI Shapefile"
                )
                
                # Gestion des erreurs compatible avec QGIS 3.4 et 3.10+
                if isinstance(error, tuple):
                    # QGIS 3.10+
                    if error[0] != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error[1]}")
                else:
                    # QGIS 3.4
                    if error != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error}")
                    
            elif extension == '.geojson':
                # Export GeoJSON - compatible avec QGIS 3.4+
                # Utiliser la version ancienne compatible avec QGIS 3.4
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    active_layer,
                    temp_path,
                    "utf-8",
                    active_layer.crs(),
                    "GeoJSON"
                )
                
                # Gestion des erreurs compatible avec QGIS 3.4 et 3.10+
                if isinstance(error, tuple):
                    # QGIS 3.10+
                    if error[0] != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error[1]}")
                else:
                    # QGIS 3.4
                    if error != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error}")
                    
            elif extension == '.kml':
                # Export KML - compatible avec QGIS 3.4
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    active_layer,
                    temp_path,
                    "utf-8",
                    active_layer.crs(),
                    "KML"
                )
                
                # Gestion des erreurs compatible avec QGIS 3.4 et 3.10+
                if isinstance(error, tuple):
                    # QGIS 3.10+
                    if error[0] != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error[1]}")
                else:
                    # QGIS 3.4
                    if error != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error}")
                    
            elif extension == '.csv':
                # Export CSV - compatible avec QGIS 3.4
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    active_layer,
                    temp_path,
                    "utf-8",
                    active_layer.crs(),
                    "CSV"
                )
                
                # Gestion des erreurs compatible avec QGIS 3.4 et 3.10+
                if isinstance(error, tuple):
                    # QGIS 3.10+
                    if error[0] != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error[1]}")
                else:
                    # QGIS 3.4
                    if error != QgsVectorFileWriter.NoError:
                        raise Exception(f"Erreur d'export: {error}")
                    
            elif extension in ['.tif', '.jpg', '.png']:
                # Export raster - Version compatible avec QGIS 3.4+
                from qgis.core import QgsRasterFileWriter
                
                format_map = {
                    '.tif': 'GTiff',
                    '.jpg': 'JPEG',
                    '.png': 'PNG'
                }
                
                # Méthode alternative pour l'exportation raster compatible avec QGIS 3.4
                writer = QgsRasterFileWriter(temp_path)
                writer.setOutputFormat(format_map[extension])
                
                provider = active_layer.dataProvider()
                pipe = QgsRasterPipe()
                pipe.set(provider.clone())
                
                # Dans QGIS 3.4, la signature de writeRaster est légèrement différente
                error = writer.writeRaster(
                    pipe,
                    provider.xSize(),
                    provider.ySize(),
                    provider.extent(),
                    provider.crs()
                )
                
                if error != QgsRasterFileWriter.NoError:
                    raise Exception(f"Erreur d'export raster: {error}")
            else:
                raise Exception(f"Format non supporté: {extension}")
            
            self.status_label.setText(f"🔄 Téléversement de {file_name} vers WebDAV...")
            
            # Pour les shapefiles, nous devons téléverser tous les fichiers associés
            if extension == '.shp':
                # Trouver tous les fichiers associés au shapefile dans le répertoire temporaire
                base_name = os.path.splitext(file_name)[0]
                associated_files = [f for f in os.listdir(temp_dir) 
                                  if f.startswith(base_name) and f.endswith(('.shp', '.shx', '.dbf', '.prj', '.qpj', '.cpg'))]
                
                # Téléverser chaque fichier
                for associated_file in associated_files:
                    local_path = os.path.join(temp_dir, associated_file)
                    self._upload_file_to_webdav(local_path, associated_file)
            else:
                # Téléverser le fichier normal
                self._upload_file_to_webdav(temp_path, file_name)
            
            # Nettoyer les fichiers temporaires
            shutil.rmtree(temp_dir)
            
            self.status_label.setText(f"✅ Couche enregistrée sur WebDAV: {file_name}")
            self.refresh_webdav_content()  # Rafraîchir pour voir le nouveau fichier
            
            QMessageBox.information(self, "Succès", 
                                  f"Couche enregistrée avec succès sur WebDAV!\n\n"
                                  f"📄 {file_name}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer la couche:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def save_current_project_to_webdav(self):
        """Enregistre le projet QGIS actuel sur le serveur WebDAV"""
        try:
            # Importer les modules nécessaires
            import os, tempfile
            from qgis.utils import iface  # Import explicite de iface
            
            # Vérifier si une connexion est active
            if not self.current_connection or not hasattr(self, 'current_path'):
                QMessageBox.warning(self, "Erreur", "Aucune connexion WebDAV active")
                return False
            
            # Obtenir le projet actuel
            project = QgsProject.instance()
            
            # Demander le nom du fichier projet
            current_project_file = project.fileName()
            suggested_name = os.path.basename(current_project_file) if current_project_file else "projet.qgz"
            
            # Si le projet n'a pas encore été enregistré, suggérer un nom par défaut
            if not suggested_name or suggested_name == '.qgz':
                suggested_name = "projet.qgz"
            
            file_name, ok = QInputDialog.getText(self, "Nom du projet", 
                                              "Nom du fichier projet:", QLineEdit.Normal, 
                                              suggested_name)
            if not ok or not file_name:
                return False
            
            # Ajouter l'extension si elle n'est pas présente
            if not file_name.lower().endswith(('.qgs', '.qgz')):
                file_name += '.qgz'  # Format par défaut
            
            # Créer un fichier temporaire
            temp_dir = tempfile.mkdtemp(prefix="qgis_webdav_project_")
            temp_path = os.path.join(temp_dir, file_name)
            
            self.status_label.setText(f"🔄 Préparation du projet pour {file_name}...")
            
            # Demander si les chemins des couches doivent être relatifs ou absolus
            options = ["Chemins absolus", "Chemins relatifs (recommandé pour le WebDAV)"]
            path_choice, ok = QInputDialog.getItem(self, "Type de chemins", 
                                                "Comment stocker les chemins des couches?",
                                                options, 1, False)
            if not ok:
                return False
            
            # Configurer les options du projet
            if path_choice == options[1]:  # Chemins relatifs
                project.writeEntryBool("Paths", "Absolute", False)
            else:
                project.writeEntryBool("Paths", "Absolute", True)
            
            # Enregistrer le projet temporairement
            if project.write(temp_path):
                # Téléverser le fichier projet
                self.status_label.setText(f"🔄 Téléversement du projet {file_name} vers WebDAV...")
                self._upload_file_to_webdav(temp_path, file_name)
                
                # Nettoyer les fichiers temporaires
                shutil.rmtree(temp_dir)
                
                self.status_label.setText(f"✅ Projet enregistré sur WebDAV: {file_name}")
                self.refresh_webdav_content()  # Rafraîchir pour voir le nouveau fichier
                
                QMessageBox.information(self, "Succès", 
                                      f"Projet enregistré avec succès sur WebDAV!\n\n"
                                      f"📄 {file_name}")
                return True
            else:
                raise Exception("Échec de l'enregistrement du projet")
            
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le projet:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def _upload_file_to_webdav(self, local_file_path, target_filename=None):
        """
        Méthode interne pour téléverser un fichier vers le WebDAV actuel
        """
        import os
        
        # Déterminer le nom de fichier cible s'il n'est pas spécifié
        if not target_filename:
            target_filename = os.path.basename(local_file_path)
        
        # Construire l'URL de destination
        target_url = self.current_connection['url']
        if not target_url.endswith('/'):
            target_url += '/'
        
        # Ajouter le chemin actuel s'il est défini
        if hasattr(self, 'current_path') and self.current_path and self.current_path != '/':
            # Enlever le slash initial si présent pour éviter la duplication
            path_part = self.current_path
            if path_part.startswith('/'):
                path_part = path_part[1:]
            
            # Assurer que le chemin se termine par un slash
            if not path_part.endswith('/'):
                path_part += '/'
                
            target_url += path_part
        
        # Ajouter le nom de fichier
        target_url += target_filename
        
        # Nettoyer l'URL (pour éviter les problèmes de duplication NextCloud)
        target_url = self.clean_nextcloud_url(target_url)
        
        # Dernière vérification - nettoyage sanitaire de l'URL
        target_url = self.sanitize_webdav_url(target_url)
        print(f"⚡ URL FINALE pour upload: {target_url}")
        
        # Ouvrir le fichier local
        with open(local_file_path, 'rb') as file:
            file_content = file.read()
        
        # Téléverser avec authentification si nécessaire
        if self.current_connection.get('username'):
            self.session.auth = HTTPBasicAuth(
                self.current_connection['username'],
                self.current_connection['password']
            )
        
        # Téléverser le fichier
        response = self.session.put(target_url, data=file_content)
        
        if response.status_code not in [200, 201, 204]:
            raise Exception(f"Erreur lors du téléversement: {response.status_code} - {response.text}")
        
        return True
    
    def configure_shared_link_auth(self):
        """Configure l'authentification pour un lien partagé"""
        if not self.is_nextcloud_shared_link():
            return False
            
        # Cas 1: Lien CRAIG opendata
        if 'craig.fr/s/opendata' in self.current_connection.get('url', '').lower():
            if not self.current_connection.get('username'):
                self.current_connection['username'] = 'opendata'
                self.status_label.setText("🔑 Configuration spéciale pour CRAIG OpenData")
                return True
                
        # Cas 2: Autres liens partagés publics (sans authentification)
        # Nextcloud permet parfois l'accès sans authentification aux liens partagés
        share_info = self.get_nextcloud_share_info()
        if share_info and not self.current_connection.get('username'):
            self.status_label.setText("🔓 Configuration pour lien partagé public")
            # On peut éventuellement définir un nom d'utilisateur "invité" ou laisser vide
            return True
            
        return False
    
    def fix_shared_link_path(self, path):
        """
        Fonction spéciale qui nettoie et corrige les chemins pour les liens partagés Nextcloud.
        Traite en particulier les duplications de 'public.php/webdav' dans les chemins.
        """
        if not self.current_mode == "nextcloud_share" or not path:
            return path
        
        # Cas spécial pour CRAIG avec sous-dossiers
        base_url = self.current_connection.get('url', '').lower()
        if 'craig.fr' in base_url and '/s/opendata' in base_url:
            # Si un sous-dossier a été spécifié dans l'URL de base, on doit l'ajouter au chemin
            # Par exemple, si URL = "https://drive.opendata.craig.fr/s/opendata/ortho"
            if '/s/opendata/' in base_url and len(base_url.split('/s/opendata/')) > 1:
                subdirectory = base_url.split('/s/opendata/')[1].strip('/')
                if subdirectory:
                    print(f"⚡ Sous-dossier CRAIG détecté: {subdirectory}")
                    
                    # Si le chemin actuel est la racine, utiliser directement le sous-dossier
                    if path == '/':
                        path = f"/{subdirectory}/"
                        print(f"⚡ Chemin CRAIG corrigé avec sous-dossier: {path}")
                        return path
                    else:
                        # Vérifier si le sous-dossier est déjà inclus dans le chemin
                        if not path.startswith(f"/{subdirectory}") and not f"/{subdirectory}/" in path:
                            path = f"/{subdirectory}{path if path.startswith('/') else '/' + path}"
                            print(f"⚡ Chemin CRAIG corrigé avec sous-dossier: {path}")
                            return path
            
        # 1. Suppression des duplications de public.php/webdav
        if path.count('public.php/webdav') > 1:
            # Garder seulement le chemin après la dernière occurrence
            parts = path.split('public.php/webdav/')
            if len(parts) > 1:
                # Reconstruire le chemin avec une seule occurrence
                path = parts[-1]  # Prendre seulement la dernière partie
                if not path.startswith('/'):
                    path = '/' + path
                print(f"⚡ Chemin corrigé pour lien partagé: {path}")
        
        # 2. S'assurer que le chemin commence par /
        if not path.startswith('/'):
            path = '/' + path
            
        return path
    
    def sanitize_webdav_url(self, url):
        """
        Fonction de dernier recours qui nettoie les URL WebDAV juste avant leur utilisation
        pour éliminer les duplications connues et autres problèmes fréquents.
        """
        if not url:
            return url
            
        # 1. Duplication de 'public.php/webdav' (cas CRAIG)
        if 'public.php/webdav/public.php/webdav' in url:
            url = url.replace('public.php/webdav/public.php/webdav', 'public.php/webdav')
            print(f"⚠️ Correction duplication 'public.php/webdav': {url}")
            
        # 2. Duplication de 'remote.php/dav' (cas Nextcloud standard)
        if 'remote.php/dav/remote.php/dav' in url:
            url = url.replace('remote.php/dav/remote.php/dav', 'remote.php/dav')
            print(f"⚠️ Correction duplication 'remote.php/dav': {url}")
            
        # 3. Préserver le protocole
        if url.startswith('http:/') and not url.startswith('http://'):
            url = url.replace('http:/', 'http://')
            print(f"⚠️ Correction protocole HTTP: {url}")
            
        if url.startswith('https:/') and not url.startswith('https://'):
            url = url.replace('https:/', 'https://')
            print(f"⚠️ Correction protocole HTTPS: {url}")
        
        # S'assurer que l'URL contient un hôte valide
        if '://' in url and url.split('://', 1)[1] == '':
            print(f"⚠️ URL sans hôte détectée: {url}")
            return None
        
        # 4. Double slashes (après la partie protocole)
        if '://' in url:
            protocol, rest = url.split('://', 1)
            # Ne corriger les doubles slashes que dans la partie après le protocole
            while '//' in rest:
                rest = rest.replace('//', '/')
                print(f"⚠️ Correction double slashes après protocole")
            
            url = f"{protocol}://{rest}"
            
        # 4. Autres cas spécifiques pour CRAIG
        if 'craig.fr' in url and '/s/opendata' in url:
            # Cas particulier pour les liens CRAIG
            if '/public.php/webdav/' in url and url.count('/public.php/webdav') > 1:
                # Approche radicale pour les URLs CRAIG - regarder le dernier chemin significatif
                # Utiliser une expression régulière pour extraire les parties du chemin
                patterns = [
                    r'public\.php/webdav/([^/]+/.+)', # Format /ortho/PCRS_5cm/...
                    r'public\.php/webdav/public\.php/webdav/([^/]+/.+)' # Format dupliqué
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        path = match.group(1)
                        # Reconstruire l'URL proprement
                        base = url.split('/public.php')[0]
                        url = f"{base}/public.php/webdav/{path}"
                        print(f"⚠️ Reconstruction spéciale URL CRAIG: {url}")
                        break
                        
                # Si aucun pattern ne correspond, approche de secours
                if url.count('/public.php/webdav') > 1:
                    # Force la suppression des duplications
                    parts = url.split('/public.php/webdav/')
                    if len(parts) > 1:
                        # Reconstruire avec seulement la première et la dernière partie
                        url = f"{parts[0]}/public.php/webdav/{parts[-1]}"
                        print(f"⚠️ Nettoyage forcé URL CRAIG: {url}")
        
        return url
    
    def load_raster_file_with_download(self, file_data):
        """
        Charge un fichier raster en le téléchargeant d'abord localement pour éviter les erreurs 429 (too many requests)
        Particulièrement utile pour les serveurs avec limitation comme le CRAIG
        """
        try:
            # Importer les modules nécessaires
            import os, tempfile, time
            
            self.status_label.setText(f"🔄 Téléchargement du raster {file_data['name']} localement...")
            
            # Créer un dossier temporaire pour le fichier
            temp_dir = tempfile.mkdtemp(prefix="qgis_webdav_raster_")
            temp_path = os.path.join(temp_dir, file_data['name'])
            
            # Utiliser la méthode correcte pour construire l'URL de téléchargement
            # Particulièrement important pour le CRAIG
            download_url = self.build_download_url(file_data['name'])
            
            # Si c'est un serveur CRAIG, on s'assure que l'URL est du bon format attendu
            if '/s/opendata' in self.current_connection['url']:
                # Afficher des informations détaillées de débogage
                print("="*80)
                print("DÉTAILS TÉLÉCHARGEMENT RASTER CRAIG:")
                print(f"- Nom du fichier: {file_data['name']}")
                print(f"- Chemin courant: {self.current_path}")
                print(f"- URL construite: {download_url}")
                
                # Afficher l'URL attendue comme exemple
                folder_path = self.current_path
                if folder_path.endswith('/'):
                    folder_path = folder_path[:-1]
                if 'public.php/webdav/' in folder_path:
                    folder_path = folder_path.replace('public.php/webdav/', '')
                print(f"- Format attendu: https://drive.opendata.craig.fr/s/opendata/download?path={folder_path}&files={file_data['name']}")
                print("="*80)
            
            # Petit délai pour éviter trop de requêtes
            time.sleep(1)
            
            self.status_label.setText(f"💾 Téléchargement depuis {download_url}...")
            print(f"⚡ Téléchargement du raster depuis: {download_url}")
            
            # Configurer l'authentification si nécessaire
            auth = None
            if self.current_connection.get('username'):
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(
                    self.current_connection['username'],
                    self.current_connection['password']
                )
            
            # Télécharger avec un timeout plus long pour les gros fichiers
            response = self.session.get(download_url, stream=True, timeout=120, auth=auth)
            
            if response.status_code != 200:
                # Attendre et réessayer une fois en cas d'erreur 429 (trop de requêtes)
                if response.status_code == 429:
                    self.status_label.setText(f"⚠️ Trop de requêtes, attente de 5 secondes...")
                    time.sleep(5)
                    self.status_label.setText(f"🔄 Nouvelle tentative de téléchargement...")
                    response = self.session.get(download_url, stream=True, timeout=120, auth=auth)
                    
                    if response.status_code != 200:
                        raise Exception(f"Erreur HTTP persistante après nouvelle tentative: {response.status_code}")
                else:
                    raise Exception(f"Erreur HTTP {response.status_code} - URL: {download_url}")
            
            # Télécharger le fichier avec une barre de progression
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setRange(0, 100)
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_bar.setValue(progress)
                            self.status_label.setText(f"💾 Téléchargement: {progress}%")
                        QApplication.processEvents()  # Garder l'interface réactive
            
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"✅ Téléchargé, chargement dans QGIS...")
            
            # Charger le fichier local dans QGIS
            layer = QgsRasterLayer(temp_path, file_data['name'])
            
            if layer.isValid():
                # Ajouter la couche à QGIS
                if self.create_groups_check.isChecked():
                    # Créer un groupe si demandé
                    root = QgsProject.instance().layerTreeRoot()
                    
                    # Nom du groupe basé sur la connexion actuelle
                    if hasattr(self, 'current_connection') and self.current_connection:
                        group_name = f"WebDAV - {self.current_connection['name']}"
                    else:
                        group_name = "WebDAV Explorer"
                    
                    # Trouver ou créer le groupe
                    group = root.findGroup(group_name)
                    if group is None:
                        group = root.insertGroup(0, group_name)
                    
                    # Ajouter la couche au groupe
                    QgsProject.instance().addMapLayer(layer, False)
                    group.addLayer(layer)
                else:
                    # Ajouter directement au projet
                    QgsProject.instance().addMapLayer(layer)
                
                self.status_label.setText(f"✅ Raster chargé: {file_data['name']}")
                return True
            else:
                error_msg = layer.error().message() if layer and hasattr(layer, 'error') else "Couche invalide"
                raise Exception(f"Impossible de charger le raster: {error_msg}")
                
        except Exception as e:
            self.progress_bar.setVisible(False)
            error_msg = str(e)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le raster:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False
    
    def debug_craig_path(self, folder_path, filename):
        """
        Fonction de débogage qui affiche les différentes parties d'un chemin CRAIG
        pour faciliter la compréhension et le diagnostic
        """
        print("="*80)
        print("DEBUG CHEMIN CRAIG:")
        print(f"- Chemin dossier brut: '{folder_path}'")
        
        # Sans public.php/webdav
        clean_path = folder_path
        if 'public.php/webdav/' in clean_path:
            clean_path = clean_path.replace('public.php/webdav/', '')
            print(f"- Sans public.php/webdav: '{clean_path}'")
        
        # S'assurer qu'il commence par /
        if not clean_path.startswith('/'):
            clean_path = '/' + clean_path
            print(f"- Avec slash initial: '{clean_path}'")
        
        # Supprimer le nom de fichier s'il est présent
        if clean_path.endswith('/' + filename):
            clean_path = clean_path[:-len('/' + filename)]
            print(f"- Sans le fichier: '{clean_path}'")
        elif clean_path.endswith(filename):
            clean_path = clean_path[:-len(filename)]
            print(f"- Sans le fichier: '{clean_path}'")
        
        # Supprimer le slash final
        if clean_path.endswith('/'):
            clean_path = clean_path[:-1]
            print(f"- Sans slash final: '{clean_path}'")
        
        # Encoder pour URL
        path_encoded = quote(clean_path)
        print(f"- Encodé pour URL: '{path_encoded}'")
        
        # URL finale
        base_url = self.current_connection['url']
        base_parts = base_url.split('/s/')
        if len(base_parts) > 1:
            domain = base_parts[0]
            token = base_parts[1].split('/')[0]
            download_url = f"{domain}/s/{token}/download?path={path_encoded}&files={filename}"
            print(f"- URL finale: '{download_url}'")
        
        print("="*80)
    
    def build_craig_download_url_v2(self, folder_path, filename):
        """
        Construit une URL de téléchargement spécifiquement pour le format du CRAIG
        en suivant exactement le format attendu par leur API
        """
        # Extraire le domaine et le token de partage
        base_url = self.current_connection['url'].rstrip('/')
        base_parts = base_url.split('/s/')
        if len(base_parts) < 2:
            return None  # Format non compatible
        
        domain = base_parts[0]
        token = base_parts[1].split('/')[0]  # Le token est avant le premier slash
        
        # Nettoyer le chemin du dossier
        clean_path = folder_path
        
        # Supprimer 'public.php/webdav/' du chemin s'il existe
        if 'public.php/webdav/' in clean_path:
            clean_path = clean_path.replace('public.php/webdav/', '')
        
        # S'assurer qu'il commence par /
        if not clean_path.startswith('/'):
            clean_path = '/' + clean_path
            
        # Supprimer le slash final car le format CRAIG n'en utilise pas
        if clean_path.endswith('/'):
            clean_path = clean_path[:-1]
            
        # Si c'est la racine, utiliser un slash
        if clean_path == '':
            clean_path = '/'
            
        # Encoder le chemin
        path_encoded = quote(clean_path)
        
        # Construire l'URL finale au format exact attendu par le CRAIG
        # Format : https://drive.opendata.craig.fr/s/opendata/download?path=/ortho/PCRS_5cm/2017/lyon&files=8384-65000.tif
        download_url = f"{domain}/s/{token}/download?path={path_encoded}&files={filename}"
        
        print(f"⚡ URL CRAIG construite: {download_url}")
        return download_url
    
    def load_craig_raster(self, file_data):
        """
        Fonction spéciale pour les rasters CRAIG, qui utilise directement l'URL au format correct
        pour contourner les problèmes d'erreur 429 et de formatage d'URL.
        """
        try:
            import os, tempfile, time
            
            # Extraire le nom du fichier et le chemin du dossier
            filename = file_data['name']
            folder_path = self.current_path if self.current_path != '/' else ''
            
            self.status_label.setText(f"🔄 Préparation du téléchargement CRAIG: {filename}")
            print(f"⚡ CRAIG - Chemin dossier original: '{folder_path}'")
            
            # IMPORTANT: Nettoyage complet et radical de toute occurrence de public.php/webdav
            clean_path = folder_path
            
            # Afficher le chemin avant nettoyage
            print(f"⚡ CRAIG - Nettoyage chemin brut: '{clean_path}'")
            
            # Supprimer TOUTES les occurrences de public.php/webdav sous toutes ses formes
            patterns_to_remove = [
                'public.php/webdav/',
                '/public.php/webdav/',
                'public.php/webdav',
                '/public.php/webdav'
            ]
            
            for pattern in patterns_to_remove:
                while pattern in clean_path:
                    clean_path = clean_path.replace(pattern, '')
                    print(f"⚡ CRAIG - Suppression de '{pattern}': '{clean_path}'")
            
            # S'assurer que le chemin commence par /
            if not clean_path.startswith('/'):
                clean_path = '/' + clean_path
            
            # Supprimer le nom de fichier s'il est inclus dans le chemin
            if clean_path.endswith('/' + filename):
                clean_path = clean_path[:-len('/' + filename)]
                print(f"⚡ CRAIG - Suppression du fichier du chemin: '{clean_path}'")
            elif clean_path.endswith(filename):
                clean_path = clean_path[:-len(filename)]
                print(f"⚡ CRAIG - Suppression du fichier du chemin: '{clean_path}'")
            
            # Supprimer le slash final
            if clean_path.endswith('/'):
                clean_path = clean_path[:-1]
            
            # Vérification finale pour s'assurer qu'il ne reste plus aucune trace de public.php/webdav
            if 'public.php' in clean_path or 'webdav' in clean_path:
                print(f"⚡ CRAIG - ⚠️ ATTENTION: Il reste des traces de public.php/webdav: '{clean_path}'")
                # Dernier recours: extraction directe du chemin utile
                parts = clean_path.split('/ortho/')
                if len(parts) > 1:
                    clean_path = '/ortho/' + parts[1]
                    print(f"⚡ CRAIG - Extraction directe du chemin utile: '{clean_path}'")
            
            print(f"⚡ CRAIG - Chemin final nettoyé: '{clean_path}'")
            
            # Extraire le domaine et le token
            base_url = self.current_connection['url'].rstrip('/')
            domain = base_url.split('/s/')[0]
            token = base_url.split('/s/')[1].split('/')[0]
            
            # Construire l'URL au format exact attendu par le CRAIG
            # Format CORRECT: https://drive.opendata.craig.fr/s/opendata/download?path=/ortho/PCRS_5cm/2017/lyon&files=8384-65000.tif
            # Format INCORRECT: https://drive.opendata.craig.fr/s/opendata/download?path=/public.php/webdav/ortho/PCRS_5cm/2017/lyon/8384-65000.tif
            from urllib.parse import quote
            
            # Dernière vérification pour s'assurer que le format est correct
            path_param = clean_path
            
            # Si le chemin contient encore le nom du fichier pour une raison quelconque, le supprimer
            if path_param.endswith('/' + filename):
                path_param = path_param[:-len('/' + filename)]
            
            # Si le chemin contient toujours public.php, dernier recours
            if 'public.php' in path_param:
                print(f"⚡ CRAIG - ERREUR CRITIQUE: Impossible de nettoyer complètement le chemin: {path_param}")
                # Tentative de récupération en extrayant les composants clés
                ortho_path = None
                for year in ["2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024"]:
                    if year in path_param:
                        parts = path_param.split(year)
                        if len(parts) > 1:
                            ortho_path = f"/ortho/PCRS_5cm/{year}{parts[1]}"
                            break
                
                if ortho_path:
                    path_param = ortho_path
                    print(f"⚡ CRAIG - Chemin reconstruit: {path_param}")
            
            # S'assurer que le chemin ne contient pas le nom du fichier à la fin
            if path_param.endswith('/' + filename):
                path_param = path_param[:-len('/' + filename)]
            elif path_param.endswith(filename):
                path_param = path_param[:-len(filename)]
                
            # Construction finale de l'URL
            download_url = f"{domain}/s/{token}/download?path={quote(path_param)}&files={filename}"
            
            print(f"⚡ CRAIG - URL finale: {download_url}")
            self.status_label.setText(f"🔄 Téléchargement avec URL CRAIG directe...")
            
            # Créer un dossier temporaire
            temp_dir = tempfile.mkdtemp(prefix="qgis_craig_raster_")
            temp_path = os.path.join(temp_dir, filename)
            
            # Télécharger le fichier
            time.sleep(1)  # Petit délai
            
            # Configurer l'authentification si nécessaire
            auth = None
            if self.current_connection.get('username'):
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(
                    self.current_connection['username'],
                    self.current_connection['password']
                )
            
            # Télécharger avec un timeout étendu
            response = self.session.get(download_url, stream=True, timeout=120, auth=auth)
            
            if response.status_code != 200:
                if response.status_code == 429:
                    self.status_label.setText(f"⚠️ Trop de requêtes (429), attente de 5 secondes...")
                    time.sleep(5)
                    self.status_label.setText(f"🔄 Nouvelle tentative...")
                    response = self.session.get(download_url, stream=True, timeout=120, auth=auth)
                    
                    if response.status_code != 200:
                        raise Exception(f"Erreur HTTP persistante: {response.status_code} - URL: {download_url}")
                else:
                    raise Exception(f"Erreur HTTP {response.status_code} - URL: {download_url}")
            
            # Télécharger avec barre de progression
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setRange(0, 100)
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_bar.setValue(progress)
                            self.status_label.setText(f"💾 Téléchargement CRAIG: {progress}%")
                        QApplication.processEvents()
            
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"✅ Téléchargé, chargement dans QGIS...")
            
            # Charger le raster dans QGIS
            layer = QgsRasterLayer(temp_path, filename)
            if layer.isValid():
                # Ajouter au projet
                if self.create_groups_check.isChecked():
                    root = QgsProject.instance().layerTreeRoot()
                    group_name = f"WebDAV - {self.current_connection['name']}" if 'name' in self.current_connection else "CRAIG"
                    group = root.findGroup(group_name)
                    if group is None:
                        group = root.insertGroup(0, group_name)
                    QgsProject.instance().addMapLayer(layer, False)
                    group.addLayer(layer)
                else:
                    QgsProject.instance().addMapLayer(layer)
                
                self.status_label.setText(f"✅ Raster CRAIG chargé: {filename}")
                return True
            else:
                raise Exception(f"Raster invalide après téléchargement: {layer.error().message() if hasattr(layer, 'error') else 'Erreur inconnue'}")
                
        except Exception as e:
            error_msg = str(e)
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le raster CRAIG:\n{error_msg}")
            self.status_label.setText(f"❌ Erreur: {error_msg}")
            return False