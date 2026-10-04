#!/usr/bin/env python3
"""
Aktifkan proxy Cloudflare untuk siakred.unisan.ac.id lewat Cloudflare API.

    python3 cloudflare-setup.py              # cek dulu, lalu terapkan (minta konfirmasi)
    python3 cloudflare-setup.py --rollback   # kembalikan record ke "DNS only"

Token API (dashboard Cloudflare -> My Profile -> API Tokens -> Create Token
-> Custom token), izin:
    Zone : Zone          : Read
    Zone : Zone Settings : Edit
    Zone : DNS           : Edit
    Zone : Config Rules  : Edit
Zone Resources: Include -> Specific zone -> unisan.ac.id

Token diminta secara tersembunyi (tidak tampil & tidak masuk history shell).
Kompatibel Python 3.6 (python3 bawaan Rocky Linux 8).
"""
import getpass
import json
import socket
import sys
import time
import urllib.error
import urllib.request

ZONE_NAME = "unisan.ac.id"
HOST = "siakred.unisan.ac.id"
ORIGIN_IP = "101.50.2.14"
API = "https://api.cloudflare.com/client/v4"

TOKEN = None


def cf(method, path, body=None, ok_404=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if ok_404 and e.code == 404:
            return None
        detail = e.read().decode(errors="replace")
        raise SystemExit("API %s %s gagal (%s): %s" % (method, path, e.code, detail[:400]))


def setting(zone_id, name):
    r = cf("GET", "/zones/%s/settings/%s" % (zone_id, name), ok_404=True)
    return r["result"]["value"] if r and r.get("success") else None


def set_setting(zone_id, name, value):
    cf("PATCH", "/zones/%s/settings/%s" % (zone_id, name), {"value": value})


def ask(msg):
    return input(msg + " [y/N] ").strip().lower() in ("y", "ya", "yes")


def main():
    global TOKEN
    rollback = "--rollback" in sys.argv

    TOKEN = getpass.getpass("Cloudflare API Token (tidak akan tampil): ").strip()
    if not TOKEN:
        raise SystemExit("Token kosong.")

    v = cf("GET", "/user/tokens/verify")
    if not v.get("success"):
        raise SystemExit("Token tidak valid.")

    zones = cf("GET", "/zones?name=" + ZONE_NAME)["result"]
    if not zones:
        raise SystemExit("Zona %s tidak ditemukan untuk token ini." % ZONE_NAME)
    zone_id = zones[0]["id"]

    recs = cf("GET", "/zones/%s/dns_records?type=A&name=%s" % (zone_id, HOST))["result"]
    if len(recs) != 1:
        raise SystemExit("Diharapkan 1 record A untuk %s, ditemukan %d." % (HOST, len(recs)))
    rec = recs[0]

    # ---------------- ROLLBACK ----------------
    if rollback:
        cf("PATCH", "/zones/%s/dns_records/%s" % (zone_id, rec["id"]), {"proxied": False})
        print("OK: %s kembali ke DNS only (langsung ke %s)." % (HOST, rec["content"]))
        return

    # ---------------- CEK ----------------
    if rec["content"] != ORIGIN_IP:
        raise SystemExit("Record %s mengarah ke %s, bukan %s. Batal." % (HOST, rec["content"], ORIGIN_IP))

    ssl_mode = setting(zone_id, "ssl")
    all_recs = cf("GET", "/zones/%s/dns_records?per_page=500" % zone_id)["result"]
    other_proxied = [r["name"] for r in all_recs if r.get("proxied") and r["name"] != HOST]

    print()
    print("Zona            : %s" % ZONE_NAME)
    print("Record          : %s -> %s (proxied=%s)" % (HOST, rec["content"], rec.get("proxied")))
    print("Mode SSL zona   : %s" % ssl_mode)
    print("Record proxied lain di zona: %s" % (", ".join(other_proxied) or "-"))
    print("HTTP/3          : %s" % setting(zone_id, "http3"))
    print("Early Hints     : %s" % setting(zone_id, "early_hints"))
    print("Rocket Loader   : %s" % setting(zone_id, "rocket_loader"))
    print()

    # Mode SSL: Full/Full(strict) wajib, Flexible -> redirect loop (Django paksa HTTPS)
    ssl_plan = None
    if ssl_mode in ("full", "strict"):
        print("SSL: mode '%s' sudah aman, tidak diubah." % ssl_mode)
    elif not other_proxied:
        ssl_plan = "zone"
        print("SSL: mode zona akan diubah '%s' -> 'strict' (tidak ada record proxied lain)." % ssl_mode)
    else:
        ssl_plan = "rule"
        print("SSL: mode zona '%s' TIDAK diubah (dipakai record lain)." % ssl_mode)
        print("     Akan dibuat Configuration Rule SSL=strict khusus %s." % HOST)

    plan = [
        "HTTP/3 -> on, Early Hints -> on (berlaku se-zona, aman)",
        "Record %s -> Proxied (awan oranye)" % HOST,
    ]
    print()
    for p in plan:
        print(" - " + p)
    if not ask("\nLanjutkan?"):
        print("Batal, tidak ada yang diubah.")
        return

    # ---------------- TERAPKAN ----------------
    if ssl_plan == "zone":
        set_setting(zone_id, "ssl", "strict")
        print("OK: SSL zona -> strict")
    elif ssl_plan == "rule":
        rule = {
            "description": "SIAKRED: SSL Full (strict) ke origin",
            "expression": '(http.host eq "%s")' % HOST,
            "action": "set_config",
            "action_parameters": {"ssl": "strict"},
        }
        entry = cf("GET", "/zones/%s/rulesets/phases/http_config_settings/entrypoint" % zone_id, ok_404=True)
        if entry and entry.get("success"):
            # Tambah rule ke ruleset yang ada (tidak menimpa rule lain)
            cf("POST", "/zones/%s/rulesets/%s/rules" % (zone_id, entry["result"]["id"]), rule)
        else:
            cf("PUT", "/zones/%s/rulesets/phases/http_config_settings/entrypoint" % zone_id, {"rules": [rule]})
        print("OK: Configuration Rule SSL=strict untuk %s" % HOST)

    for name in ("http3", "early_hints"):
        try:
            set_setting(zone_id, name, "on")
            print("OK: %s -> on" % name)
        except SystemExit as e:
            print("Lewati %s: %s" % (name, e))

    cf("PATCH", "/zones/%s/dns_records/%s" % (zone_id, rec["id"]), {"proxied": True})
    print("OK: %s -> Proxied" % HOST)

    # ---------------- VERIFIKASI ----------------
    print("\nMenunggu propagasi (maks. ~60 detik)...")
    for _ in range(12):
        time.sleep(5)
        try:
            ip = socket.gethostbyname(HOST)
        except socket.error:
            continue
        if ip != ORIGIN_IP:
            print("DNS publik %s sekarang -> %s (IP Cloudflare)" % (HOST, ip))
            break
    try:
        req = urllib.request.Request("https://%s/login/" % HOST, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as resp:
            print("HTTPS %s -> %s, cf-ray=%s, server=%s" % (
                HOST, resp.status, resp.headers.get("cf-ray"), resp.headers.get("server")))
    except Exception as e:
        print("Cek HTTPS gagal: %s" % e)
        print("Jika situs error, jalankan: python3 %s --rollback" % sys.argv[0])
    print("\nSelesai. Rollback kapan saja: python3 %s --rollback" % sys.argv[0])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDibatalkan.")
