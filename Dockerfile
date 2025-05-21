FROM python:3.9-slim

WORKDIR /app

# Installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code du bot
COPY bot.py .

# Créer un répertoire pour les données persistantes
RUN mkdir -p /app/data

# Commande par défaut
CMD ["python", "bot.py"]