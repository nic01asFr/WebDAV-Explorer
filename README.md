# WebDAV Explorer pour QGIS

[![QGIS Minimum Version](https://img.shields.io/badge/QGIS-3.16+-green.svg)](https://qgis.org/)
[![Version](https://img.shields.io/badge/version-1.0-blue.svg)](https://github.com/nic01asFr/WebDAV-Explorer)
[![License](https://img.shields.io/badge/license-GPL--3.0-orange.svg)](LICENSE)

Extension QGIS pour explorer et charger des données géographiques depuis des serveurs WebDAV/Nextcloud, optimisée pour le CRAIG et autres infrastructures de données géographiques.

![screenshots/apercu.png](https://docs.numerique.gouv.fr/media/1f66a9f2-df28-4c84-99e9-7703b28848be/attachments/75b5106e-91d4-432c-8cf9-378a64d6c2cd.png)

## 📋 Fonctionnalités

- **Connexion aux serveurs WebDAV** : connexion aux serveurs WebDAV, Nextcloud, ownCloud avec authentification
- **Support des liens partagés Nextcloud** : accès aux espaces partagés comme le CRAIG OpenData
- **Navigation arborescente** : exploration facile de la hiérarchie des dossiers
- **Prévisualisation** : aperçu des informations sur les fichiers géographiques
- **Filtrage avancé** : filtrage par type de fichier (raster, vecteur, etc.)
- **Chargement direct** : chargement des données directement dans QGIS
- **Explorateur de GeoPackage** : visualisation et chargement des couches internes aux GeoPackage
- **Téléchargement local** : téléchargement des fichiers pour usage local
- **Gestion optimisée des shapefiles** : chargement automatique des fichiers associés (shp, shx, dbf, etc.)
- **Support pour les projets QGIS** : chargement des projets QGIS stockés sur WebDAV
- **Chargement des fichiers CSV/Excel** : import via l'interface de QGIS
- **Import de scripts Python** : chargement dans la console Python de QGIS
- **Sauvegarde sur WebDAV** : export de couches et projets vers WebDAV

## 🔧 Installation

### Depuis le gestionnaire d'extensions QGIS

1. Dans QGIS, allez dans **Extensions > Installer/Gérer les extensions**
2. Dans l'onglet **Paramètres**, ajoutez le dépôt WebDAV Explorer : `https://github.com/nic01asFr/WebDAV-Explorer/releases/latest/download/plugins.xml`
3. Dans l'onglet **Tous**, recherchez "WebDAV Explorer" et cliquez sur **Installer**

### Installation manuelle

1. Téléchargez la dernière version depuis [la page des releases](https://github.com/nic01asFr/WebDAV-Explorer/releases)
2. Décompressez l'archive dans le dossier des extensions QGIS (`~/.qgis3/python/plugins/` sous Linux, `C:\Users\{USER}\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\` sous Windows)
3. Activez l'extension dans QGIS via **Extensions > Gérer les extensions**

## 🚀 Utilisation

### Configuration d'une connexion

1. Cliquez sur l'icône WebDAV Explorer dans la barre d'outils de QGIS
2. Cliquez sur **Ajouter une connexion**
3. Renseignez les informations :
   - **Nom** : nom descriptif pour la connexion
   - **URL** : adresse du serveur WebDAV/Nextcloud
   - **Utilisateur/Mot de passe** : informations d'authentification
   - **Chemin racine** : (optionnel) chemin initial

### Exemples de configuration

#### CRAIG OpenData (PCRS)

- **URL** : `https://drive.opendata.craig.fr/s/opendata`
- **Utilisateur** : `opendata`
- **Mot de passe** : (laisser vide)
- **Chemin racine** : `/ortho/PCRS_5cm`

#### Nextcloud personnel

- **URL** : `https://moncloud.example.com/remote.php/dav/files/username`
- **Utilisateur** : votre_nom_utilisateur
- **Mot de passe** : votre_mot_de_passe
- **Chemin racine** : (dossier contenant vos données géographiques)

### Navigation et chargement des données

- Double-cliquez sur un dossier pour y accéder
- Double-cliquez sur un fichier géographique pour le charger dans QGIS
- Utilisez le filtre pour afficher seulement certains types de fichiers
- Cliquez-droit sur un fichier pour afficher les options supplémentaires

### Fonctionnalités avancées

- **Explorer un GeoPackage** : visualisez le contenu et chargez des couches spécifiques
- **Charger des shapefiles** : le plugin récupère automatiquement tous les fichiers associés
- **Ouvrir des projets QGIS** : chargez des projets stockés sur WebDAV
- **Importer des CSV/Excel** : utilise l'interface standard de QGIS pour l'import
- **Charger des scripts Python** : importez directement dans la console Python
- **Sauvegarder sur WebDAV** : exportez couches et projets vers le serveur

## 🔍 Support spécial pour le CRAIG OpenData

Cette extension est spécialement optimisée pour accéder aux données du [CRAIG (Centre Régional Auvergne-Rhône-Alpes de l'Information Géographique)](https://www.craig.fr), notamment le PCRS (Plan Corps de Rue Simplifié) et autres données orthophotographiques.

Caractéristiques spécifiques pour le CRAIG :
- Gestion optimisée des grands rasters (orthophotos)
- Contournement des limitations de requêtes (erreur 429)
- Format d'URL spécial pour les téléchargements

## 🛠️ Dépannage

### Erreurs de connexion

- **Erreur 401** : vérifiez vos identifiants
- **Erreur 404** : vérifiez l'URL du serveur et le chemin
- **Erreur 429** : trop de requêtes, le plugin tentera automatiquement de contourner cette limitation

### Problèmes de chargement

- Pour les **shapefiles** : assurez-vous que tous les fichiers associés (.shp, .shx, .dbf) sont présents
- Pour les **rasters volumineux** : le plugin télécharge d'abord en local pour éviter les erreurs

## 📝 Contribution

Les contributions sont les bienvenues ! Veuillez suivre ces étapes :

1. Forkez le projet
2. Créez votre branche de fonctionnalité (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Commitez vos changements (`git commit -m 'Ajout de fonctionnalité X'`)
4. Poussez vers la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Ouvrez une Pull Request

## 📄 Licence

Ce projet est sous licence [GNU General Public License v3.0](LICENSE) - voir le fichier LICENSE pour plus de détails.

## 👤 Auteur

**Nicolas LAVAL**

## 🙏 Remerciements

- [CRAIG](https://www.craig.fr) pour leur service OpenData
- [QGIS](https://qgis.org) pour l'excellent SIG open-source 
