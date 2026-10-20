# Depiqo platform. Staging: DEPIQO_ENV=staging with the sandbox (shows STAGING). Never production without real
# partners (see docs/DEPLOY.md). The database and documents live on a volume at /data.
FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m depiqo && mkdir -p /data && chown depiqo /data && chmod 0755 deploy/entrypoint.sh
ENV DATABASE_PATH=/data/depiqo.sqlite3 STORAGE_DIR=/data/storage PORT=8000
EXPOSE 8000
# The entrypoint fixes the owner of a freshly mounted volume (hosts mount it as root), then drops to user depiqo.
ENTRYPOINT ["/srv/deploy/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn -w 3 -b 0.0.0.0:${PORT} --access-logfile - run:app"]
