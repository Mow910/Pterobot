import discord
from discord.ext import commands, tasks
import requests
import json
import datetime
import asyncio
import os
from dotenv import load_dotenv
import random
import time

# Charger les variables d'environnement (pour le développement local)
if os.path.exists(".env"):
    load_dotenv()

# Configuration
PTERODACTYL_API_URL = os.environ.get("PTERODACTYL_API_URL")
PTERODACTYL_API_KEY = os.environ.get("PTERODACTYL_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
NOTIFICATION_CHANNEL_ID = int(os.environ.get("NOTIFICATION_CHANNEL_ID", "0"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
STATUS_UPDATE_INTERVAL = int(os.environ.get("STATUS_UPDATE_INTERVAL", "900"))  # 15 minutes par défaut
SERVER_ICON = os.environ.get("SERVER_ICON", "https://i.imgur.com/YPVEOxC.png")  # Icône par défaut
AUTO_POST_STATS = os.environ.get("AUTO_POST_STATS", "true").lower() == "true"  # Activer l'affichage automatique


# Ajouter ces variables au début du fichier
CONNECTION_PATTERNS = {
    "minecraft": "joined the game",
    "project_zomboid": "Player * connected",
    "ark": "joined this ARK",
    "valheim": "Got connection SteamID",
    "rust": "joined [",
    "general": "connected"  # Pattern générique
}

DISCONNECTION_PATTERNS = {
    "minecraft": "left the game",
    "project_zomboid": "Player * disconnected",
    "ark": "left this ARK",
    "valheim": "Closing socket",
    "rust": "disconnected:",
    "general": "disconnected"  # Pattern générique
}
# Fonction pour détecter les connexions/déconnexions dans les logs
def detect_player_event(log_text, patterns, server_type=None):
    # Si le type de serveur est spécifié, utiliser uniquement ce pattern
    if server_type and server_type in patterns:
        pattern = patterns[server_type]
        if "*" in pattern:  # Pattern avec extraction de nom au milieu
            before, after = pattern.split("*")
            if before in log_text and after in log_text:
                player_part = log_text.split(before)[1].split(after)[0].strip()
                return player_part
        elif pattern in log_text:  # Pattern simple
            # Extraire le nom selon le type de serveur
            if server_type == "minecraft":
                try:
                    return log_text.split("[INFO]: ")[1].split(" " + pattern)[0]
                except:
                    pass
            elif server_type == "ark":
                try:
                    return log_text.split(": ")[1].split(" " + pattern)[0]
                except:
                    pass
            # Ajouter d'autres formats spécifiques ici
            
    # Sinon, essayer tous les patterns
    else:
        for srv_type, pattern in patterns.items():
            if "*" in pattern:  # Pattern avec extraction de nom au milieu
                before, after = pattern.split("*")
                if before in log_text and after in log_text:
                    player_part = log_text.split(before)[1].split(after)[0].strip()
                    return player_part
            elif pattern in log_text:  # Pattern simple
                # Extraire le nom selon le type de serveur
                if srv_type == "minecraft":
                    try:
                        return log_text.split("[INFO]: ")[1].split(" " + pattern)[0]
                    except:
                        pass
                elif srv_type == "project_zomboid":
                    try:
                        return log_text.split("Player ")[1].split(" " + pattern.replace("Player * ", ""))[0]
                    except:
                        pass
                elif srv_type == "ark":
                    try:
                        return log_text.split(": ")[1].split(" " + pattern)[0]
                    except:
                        pass
                # Ajouter d'autres formats spécifiques
                
    return None  # Aucun joueur détecté

# Couleurs pour les embeds
COLORS = {
    "success": 0x43B581,  # Vert
    "error": 0xF04747,    # Rouge
    "info": 0x7289DA,     # Bleu Discord
    "warning": 0xFAA61A,  # Orange
    "online": 0x43B581,   # Vert (serveur en ligne)
    "offline": 0xF04747,  # Rouge (serveur hors ligne)
    "starting": 0xFAA61A, # Orange (serveur en démarrage)
    "stopping": 0xFAA61A, # Orange (serveur en arrêt)
    "connection": 0x3BA55C,  # Vert clair (connexion de joueur)
    "disconnection": 0xEC4245,  # Rouge clair (déconnexion de joueur)
    "resources": 0x5865F2  # Bleu indigo (ressources du serveur)
}

# Chemin vers le fichier de whitelist
WHITELIST_FILE = "/app/data/whitelist.json"

# Structure pour stocker les infos des serveurs
servers_cache = {}

# Structure pour stocker les messages de statut postés
status_messages = {}

# Structure pour stocker les joueurs connectés
connected_players = {}

# Structure pour stocker l'état précédent des serveurs
previous_server_states = {}

# Charger la whitelist depuis le fichier JSON ou l'environnement
def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    
    # Fallback à la variable d'environnement
    return [int(id) for id in os.environ.get("WHITELIST", "").split(",") if id]

# Sauvegarder la whitelist dans le fichier JSON
def save_whitelist(whitelist):
    os.makedirs(os.path.dirname(WHITELIST_FILE), exist_ok=True)
    with open(WHITELIST_FILE, "w") as f:
        json.dump(whitelist, f)

# Liste des utilisateurs autorisés (ID Discord)
WHITELIST = load_whitelist()

# Intents
intents = discord.Intents.default()
intents.message_content = True

# Création du bot
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')  # Supprimer la commande d'aide par défaut

# Headers pour les requêtes API Pterodactyl
headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + PTERODACTYL_API_KEY
}

# Fonction pour vérifier si un utilisateur est dans la whitelist
def is_whitelisted(ctx):
    return ctx.author.id in WHITELIST

# Fonction d'envoi sécurisé de messages
async def safe_send(ctx, content=None, embed=None):
    try:
        return await ctx.send(content=content, embed=embed)
    except discord.Forbidden:
        print(f"Erreur de permission: Impossible d'envoyer un message dans le canal {ctx.channel.id}")
        try:
            await ctx.author.send(
                f"Je n'ai pas la permission d'envoyer des messages dans le canal {ctx.channel.name}. "
                f"Veuillez vérifier mes permissions ou contactez un administrateur."
            )
        except:
            print(f"Impossible d'envoyer un message privé à {ctx.author.id}")
    except Exception as e:
        print(f"Erreur lors de l'envoi d'un message: {str(e)}")

# Fonction pour obtenir un emoji selon le statut du serveur
def get_status_emoji(status):
    if status == "running":
        return "🟢"
    elif status == "starting":
        return "🟡"
    elif status == "stopping":
        return "🟠"
    else:
        return "🔴"

# Fonction pour formatter la taille en unités lisibles
def format_size(bytes_size):
    # Convertir en Mo
    mb_size = bytes_size / (1024 * 1024)
    
    if mb_size < 1000:
        return f"{mb_size:.2f} MB"
    else:
        # Convertir en Go
        gb_size = mb_size / 1024
        return f"{gb_size:.2f} GB"

# Fonction pour récupérer tous les serveurs disponibles
async def fetch_servers():
    global servers_cache
    try:
        print(f"Récupération des serveurs depuis {PTERODACTYL_API_URL}/api/client...")
        response = requests.get(
            f"{PTERODACTYL_API_URL}/api/client",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            servers = data.get("data", [])
            
            # Mettre à jour le cache des serveurs
            temp_cache = {}
            for server in servers:
                attributes = server.get("attributes", {})
                server_id = attributes.get("identifier", "")
                
                if server_id:
                    # Extraire les allocations
                    allocations = []
                    allocs_data = attributes.get("relationships", {}).get("allocations", {}).get("data", [])
                    for alloc in allocs_data:
                        alloc_attr = alloc.get("attributes", {})
                        allocations.append({
                            "ip": alloc_attr.get("ip", ""),
                            "alias": alloc_attr.get("ip_alias", ""),
                            "port": alloc_attr.get("port", 0),
                            "is_default": alloc_attr.get("is_default", False)
                        })
                    
                    # Stocker les informations du serveur
                    temp_cache[server_id] = {
                        "name": attributes.get("name", "Serveur sans nom"),
                        "node": attributes.get("node", "Nœud inconnu"),
                        "uuid": attributes.get("uuid", ""),
                        "description": attributes.get("description", ""),
                        "allocations": allocations,
                        "limits": attributes.get("limits", {}),
                        "is_owner": attributes.get("server_owner", False),
                        "status": None,  # Sera mis à jour par check_server_status
                        "resources": {}  # Sera mis à jour par check_server_status
                    }
            
            # Mettre à jour la cache
            servers_cache = temp_cache
            print(f"✅ {len(servers_cache)} serveurs récupérés avec succès")
            return servers_cache
        else:
            print(f"❌ Erreur lors de la récupération des serveurs: {response.status_code}")
            if response.status_code == 401:
                print("⚠️ Erreur d'authentification. Vérifiez votre clé API.")
            elif response.status_code == 404:
                print("⚠️ URL de l'API introuvable. Vérifiez l'URL du panel.")
            
            try:
                error_details = response.json()
                print(f"Détails de l'erreur: {json.dumps(error_details, indent=2)}")
            except:
                print(f"Réponse: {response.text[:200]}")
                
            return {}
    except Exception as e:
        print(f"❌ Exception lors de la récupération des serveurs: {str(e)}")
        return {}

# Fonction pour générer une barre de progression
def progress_bar(percent):
    filled = "█" * int(percent / 10)
    empty = "░" * (10 - int(percent / 10))
    return f"{filled}{empty} {percent}%"

# Fonction pour créer un embed de statut du serveur
def create_server_status_embed(server_id, server_info, resources):
    status = resources.get("current_state", "offline")
    status_emoji = get_status_emoji(status)
    status_text = {
        "running": "En ligne",
        "starting": "En démarrage",
        "stopping": "En arrêt",
        "offline": "Hors ligne"
    }.get(status, status)
    
    # Adresse du serveur
    server_address = "Non disponible"
    for alloc in server_info.get("allocations", []):
        if alloc.get("is_default", False):
            ip = alloc.get("alias") or alloc.get("ip", "")
            port = alloc.get("port", "")
            if ip and port:
                server_address = f"{ip}:{port}"
                break
    
    # Création de l'embed
    embed = discord.Embed(
        title=f"{status_emoji} {server_info['name']} - Statut du serveur",
        description=f"**État**: {status_text}\n**Adresse**: `{server_address}`",
        color=COLORS[status if status in COLORS else "info"],
        timestamp=datetime.datetime.now()
    )
    
    # Ajouter le nœud et la description si disponibles
    if server_info.get("node"):
        embed.add_field(name="Node", value=server_info["node"], inline=True)
    
    if server_info.get("description"):
        embed.add_field(name="Description", value=server_info["description"], inline=True)
    
    # Si le serveur est en ligne, ajouter les ressources
    if status == "running" and resources.get("resources"):
        res = resources["resources"]
        
        # Limites du serveur
        limits = server_info.get("limits", {})
        
        # CPU
        cpu = res.get("cpu_absolute", 0)
        cpu_percent = min(int(cpu), 100)
        embed.add_field(
            name="🔄 CPU",
            value=f"```{progress_bar(cpu_percent)}```\n{cpu:.2f}% utilisé",
            inline=False
        )
        
        # Mémoire
        memory = res.get("memory_bytes", 0)
        memory_max = limits.get("memory", 0)
        if memory_max > 0:
            memory_percent = int((memory / (memory_max * 1024 * 1024) * 100) if memory_max else 0)
            memory_text = f"```{progress_bar(memory_percent)}```\n{format_size(memory)} / {memory_max} MB"
        else:
            memory_text = f"{format_size(memory)} / Illimité"
        
        embed.add_field(name="💾 Mémoire", value=memory_text, inline=False)
        
        # Disque
        disk = res.get("disk_bytes", 0)
        disk_max = limits.get("disk", 0)
        if disk_max > 0:
            disk_percent = int((disk / (disk_max * 1024 * 1024) * 100) if disk_max else 0)
            disk_text = f"```{progress_bar(disk_percent)}```\n{format_size(disk)} / {disk_max} MB"
        else:
            disk_text = f"{format_size(disk)} / Illimité"
        
        embed.add_field(name="💿 Disque", value=disk_text, inline=False)
        
        # Joueurs connectés
        players = server_info.get("players", {})
        player_count = len(players)
        if player_count > 0:
            player_list = []
            for player_name, player_data in players.items():
                connect_time = player_data.get("connect_time", datetime.datetime.now())
                duration = datetime.datetime.now() - connect_time
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                player_list.append(f"• **{player_name}** - Connecté depuis {hours:02}:{minutes:02}:{seconds:02}")
            
            embed.add_field(
                name=f"👥 Joueurs ({player_count})",
                value="\n".join(player_list) if player_list else "Aucun joueur connecté",
                inline=False
            )
        else:
            embed.add_field(name="👥 Joueurs", value="Aucun joueur connecté", inline=False)
    
    embed.set_thumbnail(url=SERVER_ICON)
    embed.set_footer(text=f"Dernière mise à jour: {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    return embed

# Event: Bot prêt
@bot.event
async def on_ready():
    print(f'🚀 {bot.user.name} est connecté à Discord!')
    print(f'👥 Whitelist: {WHITELIST}')
    
    # Récupérer la liste des serveurs
    await fetch_servers()
    
    # Afficher les serveurs disponibles
    if servers_cache:
        print(f"Serveurs disponibles:")
        for server_id, server_info in servers_cache.items():
            print(f"  • {server_info['name']} (ID: {server_id})")
    else:
        print("⚠️ Aucun serveur n'a été détecté. Vérifiez vos identifiants API.")
    
    # Définir un statut personnalisé pour le bot
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"{len(servers_cache)} serveur(s)"
        )
    )
    
    # Démarrer les tâches
    check_server_status.start()
    if AUTO_POST_STATS:
        post_server_status.start()
    refresh_servers_list.start()

# Commande: Démarrer le serveur
@bot.command(name="start", help="Démarre le serveur de jeu")
async def start_server(ctx, server_id=None):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Vérifier si un ID a été spécifié ou s'il y a un seul serveur
    if server_id is None:
        if len(servers_cache) == 1:
            server_id = next(iter(servers_cache.keys()))
        else:
            servers_list = "\n".join([f"• **{info['name']}** - `!start {id}`" for id, info in servers_cache.items()])
            embed = discord.Embed(
                title="❓ Serveur non spécifié",
                description="Veuillez préciser l'ID du serveur à démarrer:",
                color=COLORS["warning"]
            )
            embed.add_field(name="Serveurs disponibles", value=servers_list, inline=False)
            await safe_send(ctx, embed=embed)
            return
    
    # Vérifier si le serveur existe
    if server_id not in servers_cache:
        await fetch_servers()  # Rafraîchir la liste des serveurs
        
        if server_id not in servers_cache:
            embed = discord.Embed(
                title="❌ Serveur introuvable",
                description=f"Le serveur avec l'ID `{server_id}` n'a pas été trouvé.",
                color=COLORS["error"]
            )
            await safe_send(ctx, embed=embed)
            return
    
    # Message de chargement
    embed = discord.Embed(
        title="⏳ Démarrage en cours...",
        description=f"Tentative de démarrage du serveur {servers_cache[server_id]['name']}",
        color=COLORS["warning"]
    )
    embed.set_thumbnail(url=SERVER_ICON)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    message = await safe_send(ctx, embed=embed)
    
    try:
        # Animation de chargement
        for i in range(3):
            embed.title = f"⏳ Démarrage en cours{'.' * (i + 1)}"
            await message.edit(embed=embed)
            await asyncio.sleep(1)
        
        response = requests.post(
            f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/power",
            headers=headers,
            json={"signal": "start"}
        )
        
        if response.status_code == 204:
            success_embed = discord.Embed(
                title="✅ Serveur démarré",
                description=f"Le serveur **{servers_cache[server_id]['name']}** a été démarré avec succès!",
                color=COLORS["success"],
                timestamp=datetime.datetime.now()
            )
            success_embed.set_thumbnail(url=SERVER_ICON)
            success_embed.add_field(name="État", value="🟡 En démarrage", inline=True)
            success_embed.add_field(name="Temps estimé", value="≈ 30-60 secondes", inline=True)
            success_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await message.edit(embed=success_embed)
        else:
            error_embed = discord.Embed(
                title="❌ Erreur de démarrage",
                description=f"Erreur lors du démarrage du serveur: Code {response.status_code}",
                color=COLORS["error"],
                timestamp=datetime.datetime.now()
            )
            error_embed.set_thumbnail(url=SERVER_ICON)
            error_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await message.edit(embed=error_embed)
    
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur de démarrage",
            description=f"Une erreur s'est produite: {str(e)}",
            color=COLORS["error"],
            timestamp=datetime.datetime.now()
        )
        error_embed.set_thumbnail(url=SERVER_ICON)
        error_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await message.edit(embed=error_embed)

# Commande: Redémarrer le serveur
@bot.command(name="restart", help="Redémarre le serveur de jeu")
async def restart_server(ctx, server_id=None):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Vérifier si un ID a été spécifié ou s'il y a un seul serveur
    if server_id is None:
        if len(servers_cache) == 1:
            server_id = next(iter(servers_cache.keys()))
        else:
            servers_list = "\n".join([f"• **{info['name']}** - `!restart {id}`" for id, info in servers_cache.items()])
            embed = discord.Embed(
                title="❓ Serveur non spécifié",
                description="Veuillez préciser l'ID du serveur à redémarrer:",
                color=COLORS["warning"]
            )
            embed.add_field(name="Serveurs disponibles", value=servers_list, inline=False)
            await safe_send(ctx, embed=embed)
            return
    
    # Vérifier si le serveur existe
    if server_id not in servers_cache:
        await fetch_servers()  # Rafraîchir la liste des serveurs
        
        if server_id not in servers_cache:
            embed = discord.Embed(
                title="❌ Serveur introuvable",
                description=f"Le serveur avec l'ID `{server_id}` n'a pas été trouvé.",
                color=COLORS["error"]
            )
            await safe_send(ctx, embed=embed)
            return
    
    # Message de chargement
    embed = discord.Embed(
        title="⏳ Redémarrage en cours...",
        description=f"Tentative de redémarrage du serveur {servers_cache[server_id]['name']}",
        color=COLORS["warning"]
    )
    embed.set_thumbnail(url=SERVER_ICON)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    message = await safe_send(ctx, embed=embed)
    
    try:
        # Animation de chargement
        for i in range(3):
            embed.title = f"⏳ Redémarrage en cours{'.' * (i + 1)}"
            await message.edit(embed=embed)
            await asyncio.sleep(1)
        
        response = requests.post(
            f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/power",
            headers=headers,
            json={"signal": "restart"}
        )
        
        if response.status_code == 204:
            success_embed = discord.Embed(
                title="✅ Serveur redémarré",
                description=f"Le serveur **{servers_cache[server_id]['name']}** a été redémarré avec succès!",
                color=COLORS["success"],
                timestamp=datetime.datetime.now()
            )
            success_embed.set_thumbnail(url=SERVER_ICON)
            success_embed.add_field(name="État", value="🟡 En redémarrage", inline=True)
            success_embed.add_field(name="Temps estimé", value="≈ 30-60 secondes", inline=True)
            success_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await message.edit(embed=success_embed)
        else:
            error_embed = discord.Embed(
                title="❌ Erreur de redémarrage",
                description=f"Erreur lors du redémarrage du serveur: Code {response.status_code}",
                color=COLORS["error"],
                timestamp=datetime.datetime.now()
            )
            error_embed.set_thumbnail(url=SERVER_ICON)
            error_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await message.edit(embed=error_embed)
    
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur de redémarrage",
            description=f"Une erreur s'est produite: {str(e)}",
            color=COLORS["error"],
            timestamp=datetime.datetime.now()
        )
        error_embed.set_thumbnail(url=SERVER_ICON)
        error_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await message.edit(embed=error_embed)

# Commande: Éteindre le serveur
@bot.command(name="stop", help="Éteint le serveur de jeu")
async def stop_server(ctx, server_id=None):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Vérifier si un ID a été spécifié ou s'il y a un seul serveur
    if server_id is None:
        if len(servers_cache) == 1:
            server_id = next(iter(servers_cache.keys()))
        else:
            servers_list = "\n".join([f"• **{info['name']}** - `!stop {id}`" for id, info in servers_cache.items()])
            embed = discord.Embed(
                title="❓ Serveur non spécifié",
                description="Veuillez préciser l'ID du serveur à arrêter:",
                color=COLORS["warning"]
            )
            embed.add_field(name="Serveurs disponibles", value=servers_list, inline=False)
            await safe_send(ctx, embed=embed)
            return
    
    # Vérifier si le serveur existe
    if server_id not in servers_cache:
        await fetch_servers()  # Rafraîchir la liste des serveurs
        
        if server_id not in servers_cache:
            embed = discord.Embed(
                title="❌ Serveur introuvable",
                description=f"Le serveur avec l'ID `{server_id}` n'a pas été trouvé.",
                color=COLORS["error"]
            )
            await safe_send(ctx, embed=embed)
            return
    
    # Message de confirmation
    confirm_embed = discord.Embed(
        title="⚠️ Confirmation d'arrêt",
        description=f"Êtes-vous sûr de vouloir arrêter le serveur **{servers_cache[server_id]['name']}**?\nCela déconnectera tous les joueurs actuellement en ligne.",
        color=COLORS["warning"]
    )
    confirm_embed.set_thumbnail(url=SERVER_ICON)
    confirm_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    confirm_message = await safe_send(ctx, embed=confirm_embed)
    
    # Ajouter des réactions pour la confirmation
    await confirm_message.add_reaction("✅")
    await confirm_message.add_reaction("❌")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_message.id
    
    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        
        if str(reaction.emoji) == "❌":
            cancel_embed = discord.Embed(
                title="🛑 Arrêt annulé",
                description="L'arrêt du serveur a été annulé.",
                color=COLORS["info"]
            )
            cancel_embed.set_thumbnail(url=SERVER_ICON)
            cancel_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await confirm_message.edit(embed=cancel_embed)
            return
        
        # Message de chargement
        loading_embed = discord.Embed(
            title="⏳ Arrêt en cours...",
            description=f"Tentative d'arrêt du serveur {servers_cache[server_id]['name']}",
            color=COLORS["warning"]
        )
        loading_embed.set_thumbnail(url=SERVER_ICON)
        loading_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await confirm_message.edit(embed=loading_embed)
        
        # Animation de chargement
        for i in range(3):
            loading_embed.title = f"⏳ Arrêt en cours{'.' * (i + 1)}"
            await confirm_message.edit(embed=loading_embed)
            await asyncio.sleep(1)
        
        response = requests.post(
            f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/power",
            headers=headers,
            json={"signal": "stop"}
        )
        
        if response.status_code == 204:
            success_embed = discord.Embed(
                title="✅ Serveur arrêté",
                description=f"Le serveur **{servers_cache[server_id]['name']}** a été arrêté avec succès!",
                color=COLORS["success"],
                timestamp=datetime.datetime.now()
            )
            success_embed.set_thumbnail(url=SERVER_ICON)
            success_embed.add_field(name="État", value="🔴 Hors ligne", inline=True)
            success_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await confirm_message.edit(embed=success_embed)
        else:
            error_embed = discord.Embed(
                title="❌ Erreur d'arrêt",
                description=f"Erreur lors de l'arrêt du serveur: Code {response.status_code}",
                color=COLORS["error"],
                timestamp=datetime.datetime.now()
            )
            error_embed.set_thumbnail(url=SERVER_ICON)
            error_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await confirm_message.edit(embed=error_embed)
    
    except asyncio.TimeoutError:
        timeout_embed = discord.Embed(
            title="⏱️ Délai expiré",
            description="Vous n'avez pas confirmé l'arrêt du serveur dans le temps imparti.",
            color=COLORS["info"]
        )
        timeout_embed.set_thumbnail(url=SERVER_ICON)
        timeout_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await confirm_message.edit(embed=timeout_embed)
    
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur d'arrêt",
            description=f"Une erreur s'est produite: {str(e)}",
            color=COLORS["error"],
            timestamp=datetime.datetime.now()
        )
        error_embed.set_thumbnail(url=SERVER_ICON)
        error_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await confirm_message.edit(embed=error_embed)

# Commande: Afficher tous les serveurs disponibles
@bot.command(name="servers", aliases=["serveurs", "list"], help="Liste tous les serveurs disponibles")
async def list_servers(ctx):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Message de chargement
    loading_embed = discord.Embed(
        title="⏳ Récupération des serveurs...",
        description="Récupération de la liste des serveurs disponibles",
        color=COLORS["info"]
    )
    message = await safe_send(ctx, embed=loading_embed)
    
    # Actualiser la liste des serveurs
    await fetch_servers()
    
    if not servers_cache:
        no_servers_embed = discord.Embed(
            title="❌ Aucun serveur trouvé",
            description="Aucun serveur n'a été trouvé. Vérifiez votre clé API et les permissions associées.",
            color=COLORS["error"],
            timestamp=datetime.datetime.now()
        )
        await message.edit(embed=no_servers_embed)
        return
    
    # Créer l'embed avec la liste des serveurs
    servers_embed = discord.Embed(
        title="🖥️ Serveurs disponibles",
        description=f"**{len(servers_cache)}** serveur(s) trouvé(s)",
        color=COLORS["info"],
        timestamp=datetime.datetime.now()
    )
    
    for server_id, server_info in servers_cache.items():
        status = server_info.get("status")
        status_emoji = get_status_emoji(status) if status else "⚪"
        
        # Rechercher l'adresse du serveur
        address = "Non disponible"
        for alloc in server_info.get("allocations", []):
            if alloc.get("is_default", False):
                ip = alloc.get("alias") or alloc.get("ip", "")
                port = alloc.get("port", "")
                if ip and port:
                    address = f"{ip}:{port}"
                    break
        
        # Créer la description du serveur
        server_desc = [
            f"**ID:** `{server_id}`",
            f"**État:** {status_emoji} {status or 'Inconnu'}",
            f"**Adresse:** `{address}`",
            f"**Node:** {server_info.get('node', 'Inconnu')}"
        ]
        
        servers_embed.add_field(
            name=f"{status_emoji} {server_info['name']}",
            value="\n".join(server_desc),
            inline=True
        )
    
    servers_embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await message.edit(embed=servers_embed)

# Commande: Afficher l'aide
@bot.command(name="aide", aliases=["commands", "help"], help="Affiche la liste des commandes disponibles")
async def custom_help(ctx):
    embed = discord.Embed(
        title="📖 Aide du Bot Pterodactyl",
        description="Voici la liste des commandes disponibles:",
        color=COLORS["info"],
        timestamp=datetime.datetime.now()
    )
    
    embed.set_thumbnail(url=SERVER_ICON)
    
    # Commandes de gestion du serveur
    server_commands = [
        ("!start [id]", "Démarre le serveur spécifié"),
        ("!restart [id]", "Redémarre le serveur spécifié"),
        ("!stop [id]", "Arrête le serveur spécifié")
    ]
    
    server_commands_text = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in server_commands])
    embed.add_field(name="🎮 Gestion des serveurs", value=server_commands_text, inline=False)
    
    # Commandes d'information
    info_commands = [
        ("!servers", "Liste tous les serveurs disponibles"),
        ("!refresh", "Force une actualisation des informations des serveurs"),
        ("!poststats", "Publie l'état actuel de tous les serveurs")
    ]
    
    info_commands_text = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in info_commands])
    embed.add_field(name="ℹ️ Informations", value=info_commands_text, inline=False)
    
    # Commandes d'administration (uniquement pour les utilisateurs whitelistés)
    if is_whitelisted(ctx):
        admin_commands = [
            ("!adduser <id>", "Ajoute un utilisateur à la whitelist"),
            ("!removeuser <id>", "Retire un utilisateur de la whitelist"),
            ("!whitelist", "Affiche la liste des utilisateurs autorisés")
        ]
        
        admin_commands_text = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in admin_commands])
        embed.add_field(name="🔒 Administration", value=admin_commands_text, inline=False)
    
    embed.add_field(
        name="📊 Surveillance automatique",
        value="Ce bot surveille automatiquement l'état de tous les serveurs et affiche les statistiques à intervalles réguliers.",
        inline=False
    )
    
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    
    await safe_send(ctx, embed=embed)

# Commande: Forcer l'actualisation des serveurs
@bot.command(name="refresh", help="Force une actualisation des informations des serveurs")
async def force_refresh(ctx):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    message = await ctx.send("⏳ Actualisation des serveurs en cours...")
    
    # Actualiser la liste des serveurs
    servers = await fetch_servers()
    
    if not servers:
        await message.edit(content="❌ Aucun serveur trouvé ou erreur lors de l'actualisation.")
        return
    
    # Actualiser les statuts
    await check_server_status()
    
    await message.edit(content=f"✅ {len(servers)} serveurs ont été actualisés avec succès!")

# Commande: Ajouter un utilisateur à la whitelist
@bot.command(name="adduser", help="Ajoute un utilisateur à la whitelist")
async def add_whitelist(ctx, user_id: int = None):
    global WHITELIST
    
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Vérifier si un ID a été spécifié
    if user_id is None:
        embed = discord.Embed(
            title="❓ ID manquant",
            description="Vous devez spécifier l'ID Discord de l'utilisateur à ajouter.\n\nExemple: `!adduser 123456789012345678`",
            color=COLORS["warning"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    if user_id in WHITELIST:
        embed = discord.Embed(
            title="⚠️ Déjà ajouté",
            description=f"L'utilisateur avec l'ID `{user_id}` est déjà dans la whitelist.",
            color=COLORS["warning"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Ajouter l'utilisateur
    WHITELIST.append(user_id)
    save_whitelist(WHITELIST)
    
    # Tenter de récupérer le nom de l'utilisateur
    user = None
    try:
        user = await bot.fetch_user(user_id)
    except:
        pass
    
    # Créer le texte de description
    if user:
        user_display = f"**{user.name}**"
    else:
        user_display = f"avec l'ID `{user_id}`"
    
    embed = discord.Embed(
        title="✅ Utilisateur ajouté",
        description=f"L'utilisateur {user_display} a été ajouté à la whitelist.",
        color=COLORS["success"],
        timestamp=datetime.datetime.now()
    )
    
    if user:
        embed.set_thumbnail(url=user.display_avatar.url)
    
    embed.add_field(name="ID Discord", value=f"`{user_id}`", inline=True)
    embed.add_field(name="Total whitelist", value=f"`{len(WHITELIST)}` utilisateur{'' if len(WHITELIST) == 1 else 's'}", inline=True)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    
    await safe_send(ctx, embed=embed)

# Commande: Retirer un utilisateur de la whitelist
@bot.command(name="removeuser", help="Retire un utilisateur de la whitelist")
async def remove_whitelist(ctx, user_id: int = None):
    global WHITELIST
    
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Vérifier si un ID a été spécifié
    if user_id is None:
        embed = discord.Embed(
            title="❓ ID manquant",
            description="Vous devez spécifier l'ID Discord de l'utilisateur à retirer.\n\nExemple: `!removeuser 123456789012345678`",
            color=COLORS["warning"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    if user_id not in WHITELIST:
        embed = discord.Embed(
            title="⚠️ Non trouvé",
            description=f"L'utilisateur avec l'ID `{user_id}` n'est pas dans la whitelist.",
            color=COLORS["warning"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Empêcher de se retirer soi-même si c'est le dernier admin
    if user_id == ctx.author.id and len(WHITELIST) == 1:
        embed = discord.Embed(
            title="🛑 Action bloquée",
            description="Vous ne pouvez pas vous retirer de la whitelist car vous êtes le dernier administrateur.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    # Retirer l'utilisateur
    WHITELIST.remove(user_id)
    save_whitelist(WHITELIST)
    
    # Tenter de récupérer le nom de l'utilisateur
    user = None
    try:
        user = await bot.fetch_user(user_id)
    except:
        pass
    
    # Créer le texte de description
    if user:
        user_display = f"**{user.name}**"
    else:
        user_display = f"avec l'ID `{user_id}`"
    
    embed = discord.Embed(
        title="✅ Utilisateur retiré",
        description=f"L'utilisateur {user_display} a été retiré de la whitelist.",
        color=COLORS["success"],
        timestamp=datetime.datetime.now()
    )
    
    if user:
        embed.set_thumbnail(url=user.display_avatar.url)
    
    embed.add_field(name="ID Discord", value=f"`{user_id}`", inline=True)
    embed.add_field(name="Total whitelist", value=f"`{len(WHITELIST)}` utilisateur{'' if len(WHITELIST) == 1 else 's'}", inline=True)
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    
    await safe_send(ctx, embed=embed)

# Commande: Afficher la liste des utilisateurs dans la whitelist
@bot.command(name="whitelist", aliases=["wl"], help="Affiche la liste des utilisateurs autorisés")
async def show_whitelist(ctx):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    embed = discord.Embed(
        title="🔒 Utilisateurs autorisés",
        description=f"`{len(WHITELIST)}` utilisateur{'' if len(WHITELIST) == 1 else 's'} dans la whitelist",
        color=COLORS["info"],
        timestamp=datetime.datetime.now()
    )
    
    # Récupérer les informations des utilisateurs
    users_info = []
    for user_id in WHITELIST:
        try:
            user = await bot.fetch_user(user_id)
            users_info.append((user.name, user_id, user.display_avatar.url))
        except:
            users_info.append((f"Inconnu ({user_id})", user_id, None))
    
    # Trier par nom d'utilisateur
    users_info.sort(key=lambda x: x[0].lower())
    
    # Ajouter les utilisateurs à l'embed
    for i, (name, user_id, avatar_url) in enumerate(users_info):
        embed.add_field(
            name=f"{i+1}. {name}",
            value=f"ID: `{user_id}`",
            inline=True
        )
    
    embed.set_footer(text=f"Demandé par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    
    await safe_send(ctx, embed=embed)

# Commande: Forcer la publication des statistiques des serveurs
@bot.command(name="poststats", help="Publie immédiatement les statistiques des serveurs")
async def force_post_stats(ctx):
    if not is_whitelisted(ctx):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'êtes pas autorisé à utiliser cette commande.",
            color=COLORS["error"]
        )
        await safe_send(ctx, embed=embed)
        return
    
    message = await ctx.send("⏳ Publication des statistiques en cours...")
    
    # Actualiser les serveurs et publier les stats
    await fetch_servers()
    await check_server_status()
    result = await post_server_status_now()
    
    if result:
        await message.edit(content=f"✅ Statistiques publiées avec succès!")
    else:
        await message.edit(content="❌ Erreur lors de la publication des statistiques.")

# Task: Vérifier l'état des serveurs
@tasks.loop(seconds=CHECK_INTERVAL)
async def check_server_status():
    global previous_server_states, servers_cache, connected_players
    
    try:
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel:
            print(f"❌ Canal de notification introuvable (ID: {NOTIFICATION_CHANNEL_ID})")
            return
        
        print(f"Vérification de l'état des serveurs ({len(servers_cache)} serveurs)...")
        
        # Parcourir tous les serveurs
        for server_id, server_info in servers_cache.items():
            try:
                # Récupérer les ressources du serveur
                resources_response = requests.get(
                    f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/resources",
                    headers=headers,
                    timeout=10
                )
                
                if resources_response.status_code == 200:
                    resources_data = resources_response.json()
                    resources = resources_data.get("attributes", {})
                    
                    # Mettre à jour les ressources dans le cache
                    servers_cache[server_id]["resources"] = resources
                    
                    # Récupérer le statut actuel
                    current_status = resources.get("current_state")
                    servers_cache[server_id]["status"] = current_status
                    
                    # Vérifier si le statut a changé
                    previous_status = previous_server_states.get(server_id)
                    
                    if previous_status is not None and previous_status != current_status:
                        # Le statut a changé, envoyer une notification
                        status_emoji = get_status_emoji(current_status)
                        status_text = {
                            "running": "En ligne",
                            "starting": "En démarrage",
                            "stopping": "En arrêt",
                            "offline": "Hors ligne"
                        }.get(current_status, current_status)
                        
                        embed = discord.Embed(
                            title=f"{status_emoji} État du serveur modifié",
                            description=f"Le serveur **{server_info['name']}** est maintenant **{status_text}**",
                            color=COLORS[current_status if current_status in COLORS else "info"],
                            timestamp=datetime.datetime.now()
                        )
                        embed.set_thumbnail(url=SERVER_ICON)
                        await channel.send(embed=embed)
                    
                    # Mettre à jour l'état précédent
                    previous_server_states[server_id] = current_status
                    
                    # Si le serveur est en ligne, vérifier les joueurs connectés
                    if current_status == "running":
                        # Récupérer les logs du serveur pour détecter les connexions/déconnexions
                        logs_response = requests.get(
                            f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/logs",
                            headers=headers,
                            timeout=10
                        )
                        
                        if logs_response.status_code == 200:
                            logs_data = logs_response.json()
                            logs = logs_data.get("data", [])
                            
                            # Initialiser le dictionnaire des joueurs pour ce serveur s'il n'existe pas
                            if server_id not in connected_players:
                                connected_players[server_id] = {}
                            
                            # Déterminer le type de serveur (pour optimiser la détection)
                            server_type = None
                            if "zomboid" in server_info.get("name", "").lower():
                                server_type = "project_zomboid"
                            elif "minecraft" in server_info.get("name", "").lower():
                                server_type = "minecraft"
                            # Vous pouvez ajouter d'autres détections basées sur le nom
                            
                            # Afficher quelques logs pour débogage
                            print(f"--- Logs du serveur {server_info['name']} ---")
                            for i, log in enumerate(logs[:3]):  # Analyser les 3 premiers logs
                                log_text = log.get("attributes", {}).get("content", "")
                                print(f"LOG {i+1}: {log_text}")
                            
                            # Analyser les logs pour détecter les connexions/déconnexions
                            for log in logs:
                                log_text = log.get("attributes", {}).get("content", "")
                                
                                # Détection des connexions
                                player_name = detect_player_event(log_text, CONNECTION_PATTERNS, server_type)
                                if player_name:
                                    # Si le joueur n'est pas déjà enregistré comme connecté
                                    if player_name not in connected_players[server_id]:
                                        connect_time = datetime.datetime.now()
                                        connected_players[server_id][player_name] = {"connect_time": connect_time}
                                        
                                        # Mettre à jour l'info dans le cache du serveur
                                        servers_cache[server_id]["players"] = connected_players[server_id]
                                        
                                        # Envoyer une notification de connexion
                                        embed = discord.Embed(
                                            title="🟢 Nouvelle connexion",
                                            description=f"**{player_name}** s'est connecté au serveur **{server_info['name']}**",
                                            color=COLORS["connection"],
                                            timestamp=connect_time
                                        )
                                        embed.set_thumbnail(url=SERVER_ICON)
                                        embed.add_field(name="Heure de connexion", value=connect_time.strftime("%H:%M:%S"), inline=True)
                                        embed.add_field(name="Joueurs en ligne", value=f"{len(connected_players[server_id])} joueur(s)", inline=True)
                                        await channel.send(embed=embed)
                                        print(f"✅ Détecté connexion de {player_name} sur {server_info['name']}")
                                
                                # Détection des déconnexions
                                player_name = detect_player_event(log_text, DISCONNECTION_PATTERNS, server_type)
                                if player_name:
                                    # Si le joueur était enregistré comme connecté
                                    if player_name in connected_players[server_id]:
                                        connect_time = connected_players[server_id][player_name]["connect_time"]
                                        disconnect_time = datetime.datetime.now()
                                        duration = disconnect_time - connect_time
                                        hours, remainder = divmod(duration.seconds, 3600)
                                        minutes, seconds = divmod(remainder, 60)
                                        
                                        # Supprimer le joueur de la liste des connectés
                                        del connected_players[server_id][player_name]
                                        
                                        # Mettre à jour l'info dans le cache du serveur
                                        servers_cache[server_id]["players"] = connected_players[server_id]
                                        
                                        # Envoyer une notification de déconnexion
                                        embed = discord.Embed(
                                            title="🔴 Déconnexion",
                                            description=f"**{player_name}** s'est déconnecté du serveur **{server_info['name']}**",
                                            color=COLORS["disconnection"],
                                            timestamp=disconnect_time
                                        )
                                        embed.set_thumbnail(url=SERVER_ICON)
                                        embed.add_field(
                                            name="Durée de session",
                                            value=f"{hours:02}:{minutes:02}:{seconds:02}",
                                            inline=False
                                        )
                                        embed.add_field(
                                            name="Connecté à",
                                            value=connect_time.strftime("%H:%M:%S"),
                                            inline=True
                                        )
                                        embed.add_field(
                                            name="Déconnecté à",
                                            value=disconnect_time.strftime("%H:%M:%S"),
                                            inline=True
                                        )
                                        embed.add_field(
                                            name="Joueurs restants",
                                            value=f"{len(connected_players[server_id])} joueur(s)",
                                            inline=False
                                        )
                                        await channel.send(embed=embed)
                                        print(f"✅ Détecté déconnexion de {player_name} sur {server_info['name']}")
                        
                        else:
                            print(f"Erreur lors de la récupération des logs du serveur {server_id}: {logs_response.status_code}")
                else:
                    print(f"Erreur lors de la récupération des ressources du serveur {server_id}: {resources_response.status_code}")
            
            except Exception as e:
                print(f"Erreur lors de la vérification du serveur {server_id}: {str(e)}")
    
    except Exception as e:
        print(f"Erreur lors de la vérification des serveurs: {str(e)}")

# Task: Rafraîchir la liste des serveurs périodiquement
@tasks.loop(minutes=15)
async def refresh_servers_list():
    print("Actualisation périodique de la liste des serveurs...")
    await fetch_servers()

# Fonction pour poster immédiatement les statistiques des serveurs
async def post_server_status_now():
    try:
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel:
            print(f"❌ Canal de notification introuvable (ID: {NOTIFICATION_CHANNEL_ID})")
            return False
        
        # Supprimer les anciens messages de statut
        for message_id in status_messages.values():
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
            except:
                pass
        
        status_messages.clear()
        
        # Créer un message de statut pour chaque serveur
        for server_id, server_info in servers_cache.items():
            embed = create_server_status_embed(
                server_id,
                server_info,
                server_info.get("resources", {})
            )
            
            message = await channel.send(embed=embed)
            status_messages[server_id] = message.id
        
        return True
    
    except Exception as e:
        print(f"Erreur lors de la publication des statistiques: {str(e)}")
        return False

# Task: Publier régulièrement le statut des serveurs
@tasks.loop(seconds=STATUS_UPDATE_INTERVAL)
async def post_server_status():
    try:
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel:
            print(f"❌ Canal de notification introuvable (ID: {NOTIFICATION_CHANNEL_ID})")
            return
        
        # Mettre à jour les messages existants ou en créer de nouveaux
        for server_id, server_info in servers_cache.items():
            try:
                # Créer l'embed mis à jour
                embed = create_server_status_embed(
                    server_id,
                    server_info,
                    server_info.get("resources", {})
                )
                
                # Si un message existe déjà pour ce serveur, le mettre à jour
                if server_id in status_messages:
                    try:
                        message = await channel.fetch_message(status_messages[server_id])
                        await message.edit(embed=embed)
                        continue
                    except:
                        # Message non trouvé, en créer un nouveau
                        pass
                
                # Créer un nouveau message
                message = await channel.send(embed=embed)
                status_messages[server_id] = message.id
            
            except Exception as e:
                print(f"Erreur lors de la mise à jour du statut du serveur {server_id}: {str(e)}")
    
    except Exception as e:
        print(f"Erreur lors de la publication des statistiques: {str(e)}")

# Lancer le bot
if __name__ == "__main__":
    # Vérifier que toutes les variables d'environnement nécessaires sont définies
    missing_vars = []
    for var in ["PTERODACTYL_API_URL", "PTERODACTYL_API_KEY", "DISCORD_TOKEN", "NOTIFICATION_CHANNEL_ID"]:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️ Variables d'environnement manquantes: {', '.join(missing_vars)}")
        exit(1)
    
    print("=" * 50)
    print(f"🚀 Démarrage du bot Discord Pterodactyl Monitor v1.0")
    print(f"📢 Canal de notification: {NOTIFICATION_CHANNEL_ID}")
    print(f"🔄 Intervalle de vérification: {CHECK_INTERVAL} secondes")
    print(f"⏱️ Intervalle de mise à jour du statut: {STATUS_UPDATE_INTERVAL} secondes")
    print(f"👥 Utilisateurs whitelistés: {len(WHITELIST)}")
    print(f"📊 Publication automatique des statistiques: {'Activée' if AUTO_POST_STATS else 'Désactivée'}")
    print("=" * 50)
    
    bot.run(DISCORD_TOKEN)