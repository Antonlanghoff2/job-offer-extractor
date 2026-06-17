# TrendRadar IA Deployment

This project uses Flask for the web application. The production entry point is `src.web_app:create_app` and the recommended local service port is `8000`.

## Prerequisites

- Ubuntu 22.04 or newer
- Python 3
- `git`
- `nginx`
- `systemd`
- Optional HTTPS: `certbot` and `python3-certbot-nginx`

## Files required for the main web app

- `models/segment_classifier.joblib`
- `data/raw/offres_france_travail.json`

Optional but recommended:

- `data/processed/metier_context_t3_2025.csv`
- `data/processed/tendances.json`

## Installation

```bash
git clone ...
cd job-offer-extractor
chmod +x deploy/install_ubuntu.sh deploy/start.sh
./deploy/install_ubuntu.sh
nano .env
```

Edit `.env` and add the France Travail credentials if the ingestion pipeline needs to refresh data.

## systemd

```bash
sudo cp deploy/trendradar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trendradar
sudo systemctl status trendradar
```

## Nginx

```bash
sudo cp deploy/nginx-trendradar.conf /etc/nginx/sites-available/trendradar
sudo ln -s /etc/nginx/sites-available/trendradar /etc/nginx/sites-enabled/trendradar
sudo nginx -t
sudo systemctl reload nginx
```

## Diagnostics

```bash
journalctl -u trendradar -f
sudo systemctl restart trendradar
sudo nginx -t
curl http://127.0.0.1:8000/health
```

## HTTPS with Certbot

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d trendradar.example.com
```

## Notes

- The web app reads project files using paths rooted at the repository location, so it does not depend on the current working directory.
- The comparison dashboard still supports an Indeed JSON file and can also import a local JSON snapshot through the web UI.
- The healthcheck endpoint is `http://127.0.0.1:8000/health`.
