#!/usr/bin/env bash
# =====================================================================
# Deploy optimasi kecepatan SIAKRED (branch perf/optimasi-kecepatan)
#
#   sudo bash /tmp/siakred-deploy/deploy-perf.sh            # tanpa HTTP/2
#   sudo bash /tmp/siakred-deploy/deploy-perf.sh --http2    # + HTTP/2
#
# --http2: di nginx, opsi http2 berlaku per port, jadi SEMUA situs di
# server ini yang listen 443 ikut memakai HTTP/2 (umumnya aman & lebih cepat).
#
# Keamanan:
#   - backup commit, .env, dan config nginx sebelum mengubah apa pun
#   - kalau smoke test gagal setelah restart -> rollback otomatis
#   - kalau `nginx -t` gagal -> config nginx lama dikembalikan
# =====================================================================
set -euo pipefail

APP=/var/www/akreditasi
DEPLOY_DIR=/tmp/siakred-deploy
BUNDLE=$DEPLOY_DIR/perf.bundle
BRANCH=perf/optimasi-kecepatan
SERVICE=gunicorn-akreditasi
NGINX_CONF=/etc/nginx/conf.d/siakred-unisan.conf
REDIS_URL_VALUE=redis://127.0.0.1:6379/3
TS=$(date +%Y%m%d-%H%M%S)

USE_HTTP2=0
[ "${1:-}" = "--http2" ] && USE_HTTP2=1

[ "$(id -u)" = 0 ] || { echo "Jalankan dengan sudo."; exit 1; }
cd "$APP"

as_app() { sudo -u nginx "$@"; }
step() { echo; echo "=== $* ==="; }

smoke_test() {
    local ok=0
    for host in siakred.unisan.ac.id siakred.unisan-g.id; do
        for path in / /login/; do
            code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
                --resolve "$host:443:127.0.0.1" "https://$host$path" || echo 000)
            echo "  $host$path -> $code"
            [ "$code" = 200 ] || ok=1
        done
    done
    return $ok
}

# ---------------------------------------------------------------------
step "1. Backup"
PREV=$(as_app git rev-parse HEAD)
echo "$PREV" > "$DEPLOY_DIR/prev_commit"
cp -a .env ".env.bak-$TS"
cp -a "$NGINX_CONF" "$NGINX_CONF.bak-$TS"
echo "  commit sebelumnya : $PREV"
echo "  .env backup       : $APP/.env.bak-$TS"
echo "  nginx backup      : $NGINX_CONF.bak-$TS"

rollback() {
    echo
    echo "!!! Smoke test gagal -> rollback ke $PREV"
    as_app git reset --hard "$PREV"
    cp -a ".env.bak-$TS" .env
    as_app venv/bin/python manage.py collectstatic --noinput -v 0 || true
    systemctl restart "$SERVICE"
    sleep 3
    smoke_test || true
    echo "Rollback selesai. Cek log: journalctl -u $SERVICE -n 100"
    exit 1
}

# ---------------------------------------------------------------------
step "2. Ambil kode dari bundle"
if [ -n "$(as_app git status --porcelain --untracked-files=no)" ]; then
    echo "  Ada perubahan lokal di $APP yang belum di-commit:"
    as_app git status --short --untracked-files=no
    echo "  Batal (tidak ada yang diubah)."
    exit 1
fi
as_app git fetch -q "$BUNDLE" "$BRANCH"
as_app git merge --ff-only FETCH_HEAD
as_app git log --oneline -1

# ---------------------------------------------------------------------
step "3. Redis client"
USE_REDIS=0
if as_app venv/bin/pip install -q --no-cache-dir "redis==8.1.0" \
   && as_app venv/bin/python -c "import redis; redis.Redis.from_url('$REDIS_URL_VALUE').ping()"; then
    USE_REDIS=1
    echo "  Redis OK ($REDIS_URL_VALUE)"
else
    echo "  Redis tidak bisa dipakai -> cache memakai file di $APP/cache"
fi

# ---------------------------------------------------------------------
step "4. .env & folder cache"
if [ "$USE_REDIS" = 1 ] && ! grep -q '^REDIS_URL=' .env; then
    printf '\n# Cache (optimasi kecepatan %s)\nREDIS_URL=%s\n' "$TS" "$REDIS_URL_VALUE" >> .env
    echo "  REDIS_URL ditambahkan"
fi
if ! grep -q '^CSRF_TRUSTED_ORIGINS=.*siakred.unisan.ac.id' .env; then
    echo "  PERINGATAN: CSRF_TRUSTED_ORIGINS di .env belum memuat https://siakred.unisan.ac.id"
fi
mkdir -p cache
chown nginx:nginx cache

# ---------------------------------------------------------------------
step "5. Django check & collectstatic"
as_app venv/bin/python manage.py check
as_app venv/bin/python manage.py collectstatic --noinput -v 0
echo "  static ber-hash: $(ls staticfiles/css | grep -E '^siakred\.[0-9a-f]{12}\.css$' | head -1)"

# ---------------------------------------------------------------------
step "6. Restart $SERVICE"
systemctl restart "$SERVICE"
sleep 3
systemctl is-active "$SERVICE"

step "7. Smoke test aplikasi"
smoke_test || rollback

# ---------------------------------------------------------------------
step "8. Kompres foto profil (asli disimpan sebagai *.orig)"
as_app venv/bin/python manage.py optimize_profile_images || echo "  (dilewati: gagal, situs tetap jalan)"

# ---------------------------------------------------------------------
step "9. nginx siakred.unisan.ac.id"
LISTEN="listen 443 ssl;"
[ "$USE_HTTP2" = 1 ] && LISTEN="listen 443 ssl http2;"

cat > "$NGINX_CONF" <<NGINX
# Dikelola oleh deploy/deploy-perf.sh ($TS). Backup: $NGINX_CONF.bak-$TS
server {
    server_name siakred.unisan.ac.id;
    client_max_body_size 50M;

    # Sembunyikan versi nginx (disamakan dengan siakred.unisan-g.id)
    server_tokens off;

    add_header Permissions-Policy "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=(), interest-cohort=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; img-src 'self' data: https: blob:; frame-src 'self' https://drive.google.com https://docs.google.com; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'" always;

    location = /favicon.ico {
        access_log off;
        log_not_found off;
    }

    # Static ber-hash (siakred.4ab244b9775f.css): isi tidak pernah berubah -> cache 1 tahun
    location ~* "^/static/(.+\.[0-9a-f]{12}\.[A-Za-z0-9]+)\$" {
        alias /var/www/akreditasi/staticfiles/\$1;
        gzip_static on;
        expires 1y;
        add_header Cache-Control "public, max-age=31536000, immutable";
        access_log off;
    }

    location /static/ {
        alias /var/www/akreditasi/staticfiles/;
        gzip_static on;
        expires 30d;
        access_log off;
    }

    location /media/ {
        alias /var/www/akreditasi/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://unix:/var/www/akreditasi/akreditasi.sock;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    $LISTEN # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/siakred.unisan.ac.id/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/siakred.unisan.ac.id/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot
}
server {
    if (\$host = siakred.unisan.ac.id) {
        return 301 https://\$host\$request_uri;
    } # managed by Certbot

    listen 80;
    server_name siakred.unisan.ac.id;
    return 404; # managed by Certbot
}
NGINX

if nginx -t; then
    systemctl reload nginx
    echo "  nginx reload OK"
else
    echo "  nginx -t GAGAL -> config lama dikembalikan"
    cp -a "$NGINX_CONF.bak-$TS" "$NGINX_CONF"
    nginx -t && systemctl reload nginx
fi

# ---------------------------------------------------------------------
step "10. Verifikasi akhir"
sleep 1
smoke_test || echo "  PERINGATAN: ada halaman yang tidak 200, cek di atas"
CSS=$(curl -s --resolve siakred.unisan.ac.id:443:127.0.0.1 https://siakred.unisan.ac.id/login/ \
      | grep -oE '/static/css/siakred\.[0-9a-f]{12}\.css' | head -1 || true)
echo "  CSS di halaman login: ${CSS:-TIDAK BER-HASH}"
if [ -n "$CSS" ]; then
    curl -sI --resolve siakred.unisan.ac.id:443:127.0.0.1 "https://siakred.unisan.ac.id$CSS" \
        | grep -iE '^(HTTP|cache-control|server):' | sed 's/^/  /'
fi
curl -sI --resolve siakred.unisan.ac.id:443:127.0.0.1 https://siakred.unisan.ac.id/ \
    | grep -iE '^(server|content-security-policy|permissions-policy):' | cut -c1-90 | sed 's/^/  /'

echo
echo "SELESAI. Rollback manual bila perlu:"
echo "  cd $APP && sudo -u nginx git reset --hard $PREV && sudo cp -a .env.bak-$TS .env \\"
echo "    && sudo -u nginx venv/bin/python manage.py collectstatic --noinput && sudo systemctl restart $SERVICE"
echo "  sudo cp -a $NGINX_CONF.bak-$TS $NGINX_CONF && sudo nginx -t && sudo systemctl reload nginx"
