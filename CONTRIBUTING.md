# Contribuer au projet WebDAV Explorer

Nous sommes ravis que vous envisagiez de contribuer au plugin WebDAV Explorer ! Voici quelques lignes directrices pour vous aider à démarrer.

## Comment contribuer

### Signaler des bugs

Si vous avez trouvé un bug, veuillez créer une issue sur GitHub avec les informations suivantes :

1. **Titre clair** décrivant le problème
2. **Description détaillée** incluant :
   - Comment reproduire le bug
   - Ce que vous attendiez qu'il se passe
   - Ce qui s'est réellement passé
   - Version de QGIS utilisée
   - Version du plugin
3. **Captures d'écran** si possible
4. **Fichiers journaux** pertinents

### Proposer des améliorations

Pour proposer de nouvelles fonctionnalités :

1. Vérifiez d'abord que cette fonctionnalité n'est pas déjà planifiée ou discutée dans les issues
2. Créez une nouvelle issue avec le label "enhancement"
3. Décrivez en détail la fonctionnalité et ses cas d'utilisation

### Soumettre des modifications

Pour contribuer au code :

1. Forker le repository
2. Créer une branche pour votre fonctionnalité (`git checkout -b feature/ma-fonctionnalite`)
3. Commiter vos changements (`git commit -am 'Ajout de ma-fonctionnalite'`)
4. Pousser vers la branche (`git push origin feature/ma-fonctionnalite`)
5. Créer une Pull Request

## Style de code

Merci de respecter ces conventions de codage :

- Suivez la [PEP 8](https://www.python.org/dev/peps/pep-0008/) pour le code Python
- Utilisez des noms de variables et de fonctions explicites
- Commentez votre code (en français de préférence)
- Ajoutez des docstrings aux fonctions et classes
- Préférez les imports explicites (`from qgis.PyQt.QtWidgets import QDockWidget`) aux imports globaux (`from qgis.PyQt.QtWidgets import *`)

## Tests

- Assurez-vous que votre code fonctionne avec la version minimale requise de QGIS (3.16+)
- Testez votre code sur plusieurs systèmes d'exploitation si possible
- Vérifiez que votre code n'introduit pas de régression

## Processus de Pull Request

1. Mettez à jour votre branche avec la branche principale avant de soumettre
2. Décrivez les changements apportés dans la description de la PR
3. Référencez les issues concernées (par exemple "Fixes #123")
4. Attendez la revue du code et apportez les modifications demandées si nécessaire

## Spécificités pour les serveurs WebDAV

Si vous ajoutez la prise en charge d'un nouveau type de serveur WebDAV/Nextcloud, veuillez documenter :

1. Les URL spécifiques et leurs formats
2. Les particularités d'authentification
3. Tout comportement spécial à gérer

## Contact

Si vous avez des questions, n'hésitez pas à contacter Nicolas LAVAL (nicolas.laval@cerema.fr). 