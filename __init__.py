#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDAV Explorer - Extension QGIS
Point d'entrée de l'extension
"""

def classFactory(iface):
    """Point d'entrée obligatoire pour QGIS"""
    from .webdav_explorer_plugin import WebDAVExplorerPlugin
    return WebDAVExplorerPlugin(iface)