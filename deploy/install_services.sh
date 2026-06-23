#!/bin/bash
# Script d'installation des services systemd pour TrendRadar IA

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Installation des services systemd pour TrendRadar IA..."

# Créer le dossier logs
mkdir -p "$PROJECT_ROOT/logs"

# Copier les fichiers systemd
sudo cp "$SCRIPT_DIR/systemd/trendradar-refresh.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/systemd/trendradar-refresh.timer" /etc/systemd/system/

# Recharger systemd
sudo systemctl daemon-reload

# Activer et démarrer le timer
sudo systemctl enable trendradar-refresh.timer
sudo systemctl start trendradar-refresh.timer

echo "✓ Services installés et démarrés"
echo ""
echo "Commandes utiles :"
echo "  sudo systemctl status trendradar-refresh.timer"
echo "  sudo systemctl status trendradar-refresh.service"
echo "  sudo journalctl -u trendradar-refresh.service -f"
echo "  sudo systemctl stop trendradar-refresh.timer"
echo "  sudo systemctl start trendradar-refresh.timer"
