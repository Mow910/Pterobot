# Pterobot
# 🚀 Bot Discord Pterodactyl Monitor

Un bot Discord puissant et élégant pour surveiller vos serveurs de jeux Pterodactyl directement depuis Discord. Recevez des notifications en temps réel sur l'état de vos serveurs, les connexions et déconnexions des joueurs, et contrôlez tout depuis Discord.

![Bot Preview]([https://i.imgur.com/YPVEOxC.png](https://i.imgur.com/5rb6VgI.png))

## ✨ Fonctionnalités

- **📊 Surveillance automatique** - Contrôle régulier de l'état de tous vos serveurs
- **🎮 Détection des joueurs** - Notifications lors des connexions et déconnexions
- **📈 Statistiques en temps réel** - Affichage de l'utilisation CPU, mémoire et disque
- **🔄 Gestion des serveurs** - Démarrer, arrêter ou redémarrer vos serveurs directement depuis Discord
- **🎭 Multi-jeux** - Compatible avec de nombreux jeux (Minecraft, Project Zomboid, ARK, Valheim, Rust, etc.)
- **🔐 Système de whitelist** - Protégez l'accès aux commandes d'administration
- **🏷️ Embeds riches** - Interface visuelle agréable avec des embeds Discord stylisés
- **🔔 Notifications** - Alertes lors des changements d'état de vos serveurs

## 🔧 Installation

### Prérequis

- Docker et Docker Compose installés sur votre machine
- Un bot Discord créé via le [Portail des développeurs Discord](https://discord.com/developers/applications)
- Une clé API Pterodactyl avec les permissions appropriées

### Mise en place

1. **Clonez ce dépôt**

```bash
git clone https://github.com/votre-username/pterodactyl-discord-bot.git
cd pterodactyl-discord-bot
```

2. **Créez un fichier `.env`**

```
PTERODACTYL_API_URL=https://votre-panel-pterodactyl.fr
PTERODACTYL_API_KEY=votre-cle-api-pterodactyl
DISCORD_TOKEN=votre-token-discord-bot
NOTIFICATION_CHANNEL_ID=id-du-canal-discord
CHECK_INTERVAL=60
STATUS_UPDATE_INTERVAL=900
SERVER_ICON=https://i.imgur.com/votre-icone.png
AUTO_POST_STATS=true
WHITELIST=id1,id2,id3
```

3. **Construisez et démarrez le conteneur Docker**

```bash
docker-compose build
docker-compose up -d
```

4. **Vérifiez les logs**

```bash
docker-compose logs -f
```

## 🎮 Utilisation

### Commandes disponibles

| Commande | Description |
|----------|-------------|
| `!start [id]` | Démarre le serveur spécifié |
| `!restart [id]` | Redémarre le serveur spécifié |
| `!stop [id]` | Arrête le serveur spécifié |
| `!servers` | Liste tous les serveurs disponibles |
| `!refresh` | Force une actualisation des informations |
| `!poststats` | Publie l'état actuel de tous les serveurs |
| `!adduser <id>` | Ajoute un utilisateur à la whitelist |
| `!removeuser <id>` | Retire un utilisateur de la whitelist |
| `!whitelist` | Affiche la liste des utilisateurs autorisés |
| `!aide` | Affiche la liste des commandes disponibles |

### Configuration avancée

#### Personnalisation des patterns de détection

Le bot est capable de détecter automatiquement les connexions et déconnexions des joueurs pour différents types de serveurs. Vous pouvez personnaliser les patterns de détection dans le fichier `bot.py` :

```python
CONNECTION_PATTERNS = {
    "minecraft": "joined the game",
    "project_zomboid": "Player * connected",
    "ark": "joined this ARK",
    # Ajoutez vos propres patterns ici
}

DISCONNECTION_PATTERNS = {
    "minecraft": "left the game",
    "project_zomboid": "Player * disconnected",
    "ark": "left this ARK",
    # Ajoutez vos propres patterns ici
}
```

## 🖼️ Captures d'écran

<!-- Insérez ici des captures d'écran du bot en action -->

## 📋 Variables d'environnement

| Variable | Description | Valeur par défaut |
|----------|-------------|-------------------|
| `PTERODACTYL_API_URL` | URL de votre panel Pterodactyl | - |
| `PTERODACTYL_API_KEY` | Clé API Pterodactyl | - |
| `DISCORD_TOKEN` | Token de votre bot Discord | - |
| `NOTIFICATION_CHANNEL_ID` | ID du canal pour les notifications | - |
| `CHECK_INTERVAL` | Intervalle de vérification en secondes | 60 |
| `STATUS_UPDATE_INTERVAL` | Intervalle de mise à jour du statut en secondes | 900 |
| `SERVER_ICON` | URL de l'icône du serveur | https://i.imgur.com/YPVEOxC.png |
| `AUTO_POST_STATS` | Activer/désactiver l'affichage automatique | true |
| `WHITELIST` | Liste des IDs Discord autorisés (séparés par des virgules) | - |

## ⚙️ Comment obtenir une clé API Pterodactyl

1. Connectez-vous à votre panel Pterodactyl
2. Allez dans la section "Account" (Compte) 
3. Cliquez sur "API Credentials" (Identifiants API)
4. Créez une nouvelle clé API avec les permissions nécessaires
   - Lecture des informations des serveurs (`r-*`)
   - Contrôle de l'alimentation des serveurs (`c-*`)

## 📜 Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.


## 🙏 Remerciements

- L'équipe [Pterodactyl](https://pterodactyl.io/) pour leur excellent panel de gestion
- La librairie [discord.py](https://discordpy.readthedocs.io/) pour l'interface Discord
