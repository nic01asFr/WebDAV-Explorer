# Changelog

Toutes les modifications notables apportées au projet WebDAV Explorer seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2023-12-10

### Ajouté
- Connexion aux serveurs WebDAV, Nextcloud et ownCloud
- Support spécial pour les liens partagés Nextcloud (CRAIG OpenData)
- Navigation dans la hiérarchie des dossiers WebDAV
- Filtrage par type de fichier (raster, vecteur, etc.)
- Prévisualisation des métadonnées de fichiers
- Chargement direct des données géographiques dans QGIS
- Explorateur de GeoPackage pour visualiser et charger des couches spécifiques
- Téléchargement local des fichiers WebDAV
- Gestion optimisée des shapefiles avec chargement automatique des fichiers associés
- Support pour les projets QGIS stockés sur WebDAV
- Import des fichiers CSV/Excel via l'interface QGIS
- Chargement des scripts Python dans la console Python de QGIS
- Sauvegarde des couches et projets vers WebDAV
- Optimisations spéciales pour les rasters CRAIG (contournement erreur 429) 