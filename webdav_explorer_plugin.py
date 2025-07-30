#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDAV Explorer - Plugin principal
"""

import os
from pathlib import Path

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon

class WebDAVExplorerPlugin:
    """Plugin principal WebDAV Explorer"""
    
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).parent
        self.dock_widget = None
        self.action = None
        
        # Initialiser les traductions
        self.init_translations()
    
    def init_translations(self):
        """Initialise les traductions"""
        try:
            locale = QSettings().value('locale/userLocale')[0:2]
            locale_path = self.plugin_dir / 'i18n' / f'webdav_explorer_{locale}.qm'
            
            if locale_path.exists():
                self.translator = QTranslator()
                self.translator.load(str(locale_path))
                QCoreApplication.installTranslator(self.translator)
        except:
            pass  # Ignore les erreurs de traduction
    
    def initGui(self):
        """Initialise l'interface graphique"""
        # Créer l'action
        icon_path = self.plugin_dir / 'icon.png'
        self.action = QAction(
            QIcon(str(icon_path)) if icon_path.exists() else QIcon(),
            'WebDAV Explorer',
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.show_dock_widget)
        self.action.setCheckable(True)
        
        # Ajouter à la barre d'outils et au menu
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToWebMenu('WebDAV Explorer', self.action)
        
        # Créer le dock widget
        self.create_dock_widget()
    
    def create_dock_widget(self):
        """Crée le widget principal"""
        try:
            from .webdav_dock_widget import WebDAVDockWidget
            
            self.dock_widget = WebDAVDockWidget(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            self.dock_widget.hide()
            
            # Connecter les signaux
            self.dock_widget.visibilityChanged.connect(self.action.setChecked)
        except Exception as e:
            print(f"Erreur création dock widget: {e}")
    
    def show_dock_widget(self):
        """Affiche/masque le dock widget"""
        if self.dock_widget and self.dock_widget.isVisible():
            self.dock_widget.hide()
        elif self.dock_widget:
            self.dock_widget.show()
    
    def unload(self):
        """Nettoie lors de la désactivation"""
        try:
            # Supprimer les éléments d'interface
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginWebMenu('WebDAV Explorer', self.action)
            
            # Fermer le dock widget
            if self.dock_widget:
                self.dock_widget.close()
                self.dock_widget = None
            
            # Nettoyer les ressources
            self.action = None
        except Exception as e:
            print(f"Erreur lors du nettoyage: {e}")