# Job Search Agent — déploiement Contabo (Playwright + Cron)
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    cron curl wget gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

RUN mkdir -p /app/storage /app/logs /app/resources
# Cron configuré au démarrage par docker-compose (évite doublon avec /etc/cron.d)
CMD ["cron", "-f"]
