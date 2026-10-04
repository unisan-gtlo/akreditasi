# Optimasi Kecepatan SIAKRED

Fokus: **siakred.unisan.ac.id** (portal resmi yang diakses pihak kampus).
`siakred.unisan-g.id` adalah domain asli; keduanya mengarah ke server yang
sama (101.50.2.14, nginx 1.14.1).

## 1. Yang berubah di kode (branch `perf/optimasi-kecepatan`)

| Area | Sebelum | Sesudah |
|---|---|---|
| Context processor (tiap halaman login) | 8+ query (5 count master, 2 notifikasi, scope + verifikasi) | 0 query saat cache hangat; dihitung ulang maks. tiap 60 dtk / 10 mnt atau saat data berubah |
| Session | `UPDATE django_session` di **setiap** klik | Dibaca dari cache; ditulis maks. 1x / 5 menit (timeout 30 menit tetap berlaku) |
| Koneksi PostgreSQL | Buka-tutup tiap request | Dipakai ulang 60 dtk (`CONN_MAX_AGE`) |
| Static (CSS/JS/logo) | Nama tetap, cache 30 hari → CSS baru bisa telat sampai ke user | Nama ber-hash (`siakred.4ab244b9775f.css`) → aman di-cache 1 tahun, update langsung terlihat |
| Logo | 500×500 px, 411 KB | 256×256 px, 20 KB |
| Beranda publik | Query SIMDA + stats setiap kunjungan | Di-cache 5 menit |
| Dokumen Saya (`butir_saya`) | 1 COUNT per butir (ratusan query) | 1 query beranotasi |
| Pohon Sesi / bundle (`_build_bundle_tree`) | 1 query per standar + per sub-standar + per butir | 4 query total |
| Dashboard Sesi (matriks instrumen×status) | 7 COUNT per instrumen | 1 query |
| Laporan (progress sesi, kelengkapan prodi, heatmap) | 2 query per dokumen (revisi terbaru + verifikasi) | 1 query untuk semua dokumen |
| Dashboard VMTS | 1 raw SQL per prodi + 4x scan tabel | 1 query + 1 scan |

## 2. Langkah deploy di server

```bash
cd /var/www/siakred            # sesuaikan
git pull
source venv/bin/activate

# Folder cache harus bisa ditulis user yang menjalankan gunicorn
mkdir -p cache && chown <user-gunicorn>: cache

python manage.py collectstatic --noinput   # WAJIB: membuat file ber-hash
sudo systemctl restart <service-gunicorn>

# Kompres foto profil yang sudah diunggah (cek dulu dengan --dry-run)
python manage.py optimize_profile_images --dry-run
python manage.py optimize_profile_images
```

Tambahkan di `.env` produksi (jika belum):

```
ALLOWED_HOSTS=siakred.unisan.ac.id,siakred.unisan-g.id
CSRF_TRUSTED_ORIGINS=https://siakred.unisan.ac.id,https://siakred.unisan-g.id
DB_CONN_MAX_AGE=60
# Opsional, jika Redis terpasang (pip install redis):
# REDIS_URL=redis://127.0.0.1:6379/1
```

Tanpa `REDIS_URL`, cache memakai file di folder `cache/`, yang tetap
dibagi antar worker gunicorn di server yang sama.

## 3. nginx untuk siakred.unisan.ac.id

Lihat `deploy/nginx/siakred.unisan.ac.id.conf` dan
`deploy/nginx/siakred-security-headers.conf`. Poin pentingnya:

- `listen 443 ssl http2`: CSS, JS, gambar dimuat paralel dalam satu koneksi.
- `ssl_session_cache` + OCSP stapling: kunjungan ulang tanpa handshake TLS penuh.
- `server_tokens off` + header keamanan disamakan dengan domain `-g.id`
  (sekarang `.ac.id` mengirim `Server: nginx/1.14.1` tanpa CSP/Permissions-Policy).
- File static ber-hash di-cache 1 tahun (`immutable`), `gzip_static on`.
- `keepalive` ke gunicorn.

Opsional tapi disarankan: upgrade nginx 1.14.1 (rilis 2018) ke versi
stabil terbaru dari repo resmi nginx.org.

## 4. Cloudflare untuk siakred.unisan.ac.id (dampak terbesar)

DNS `unisan.ac.id` **sudah** dikelola di Cloudflare, tapi record
`siakred` masih *DNS only* (awan abu-abu), jadi Cloudflare belum dipakai.
Mengaktifkan proxy (awan oranye) memberi:

- TLS diterminasi di server Cloudflare Jakarta (lebih dekat ke pengguna
  daripada server asal) → handshake lebih cepat.
- HTTP/2 + HTTP/3 (QUIC) + Brotli otomatis, tanpa upgrade nginx.
- Static ber-hash disajikan dari cache Cloudflare, tidak membebani server.

Langkah di dashboard Cloudflare (`unisan.ac.id`):

1. **DNS** → record `siakred` → ubah ke **Proxied** (oranye).
2. **SSL/TLS** → mode **Full (strict)** (sertifikat di server asal harus valid untuk `siakred.unisan.ac.id`).
3. **Speed → Optimization**: aktifkan *HTTP/3*, *Early Hints*, *Brotli*.
   **Jangan** aktifkan *Rocket Loader* (bisa merusak script inline).
4. **Caching → Cache Rules**: buat aturan
   `URI Path starts with /static/` → *Eligible for cache*, Edge TTL 1 tahun.
   **Jangan** pakai "Cache Everything" untuk HTML (halaman login berisi session/CSRF).
5. Di nginx, agar IP asli pengunjung terbaca (penting untuk django-axes & log login):

   ```nginx
   # /etc/nginx/conf.d/cloudflare-realip.conf
   # Daftar terbaru: https://www.cloudflare.com/ips/
   set_real_ip_from 173.245.48.0/20;
   set_real_ip_from 103.21.244.0/22;
   set_real_ip_from 103.22.200.0/22;
   set_real_ip_from 103.31.4.0/22;
   set_real_ip_from 141.101.64.0/18;
   set_real_ip_from 108.162.192.0/18;
   set_real_ip_from 190.93.240.0/20;
   set_real_ip_from 188.114.96.0/20;
   set_real_ip_from 197.234.240.0/22;
   set_real_ip_from 198.41.128.0/17;
   set_real_ip_from 162.158.0.0/15;
   set_real_ip_from 104.16.0.0/13;
   set_real_ip_from 104.24.0.0/14;
   set_real_ip_from 172.64.0.0/13;
   set_real_ip_from 131.0.72.0/22;
   real_ip_header CF-Connecting-IP;
   ```

   lalu di `location /` ganti
   `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` menjadi
   `proxy_set_header X-Forwarded-For $remote_addr;`.

Batasan Cloudflare (paket gratis) yang perlu diketahui:
- Upload maks. 100 MB per request (SIAKRED: 50 MB → aman).
- Request yang lebih lama dari 100 detik diputus (error 524). Jika
  download ZIP bundle untuk sesi besar lebih lama dari itu, kecualikan
  path-nya dari proxy atau buat ZIP di background.

## 5. Verifikasi setelah deploy

```bash
# Static harus ber-hash & cache 1 tahun
curl -sI https://siakred.unisan.ac.id/ | grep -i server
curl -s https://siakred.unisan.ac.id/login/ | grep -o '/static/css/siakred[^"]*'
curl -sI https://siakred.unisan.ac.id/static/css/siakred.<hash>.css | grep -i cache-control

# Waktu respons
curl -s -o /dev/null -w "tls=%{time_appconnect} ttfb=%{time_starttransfer}\n" https://siakred.unisan.ac.id/
```

Catatan pengukuran: antivirus yang memindai HTTPS (mis. AVG Web Shield)
menambah latensi TLS dan memalsukan sertifikat, jadi ukur dari perangkat
tanpa pemindaian HTTPS atau lewat https://pagespeed.web.dev.
