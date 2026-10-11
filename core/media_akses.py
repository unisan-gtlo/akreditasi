"""
Pemeriksa akses file /media/ SIAKRED untuk nginx `auth_request`.

nginx memanggil /media-akses/ (subrequest internal, membawa cookie sesi dan header
X-Original-URI) sebelum melayani file dari /var/www/akreditasi/media/.
Jawaban 204 = boleh, 401 = belum login, 403 = tidak berhak.

Aturan (sama dengan dokumen.permissions.can_view_dokumen):
- profile/, instrumen/logo/, users/foto/: publik (foto & logo halaman beranda/profil).
- dokumen/: berkas revisi dokumen. Dokumen FINAL berstatus akses TERBUKA -> publik;
  selain itu hanya pengguna yang login.
- import_master/: hanya superadmin.
- lainnya: pengguna yang login.

Akses tanpa login ke dokumen INTERNAL tetap tersedia lewat jalur Django yang memeriksa
token sendiri: tautan LED /d/<token>/ dan bundle asesor /sesi/bundle/publik/<token>/...
"""
from urllib.parse import unquote, urlsplit

from django.http import HttpResponse

PUBLIK = ("profile/", "instrumen/logo/", "users/foto/")


def path_relatif(request):
    uri = request.META.get("HTTP_X_ORIGINAL_URI", "")
    path = unquote(urlsplit(uri).path)
    if not path.startswith("/media/"):
        return None
    rel = path[len("/media/"):]
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    return rel


def media_akses(request):
    rel = path_relatif(request)
    if rel is None:
        return HttpResponse(status=403)
    if rel.startswith(PUBLIK):
        return HttpResponse(status=204)
    user = request.user
    if rel.startswith("import_master/"):
        if user.is_authenticated and user.is_superuser:
            return HttpResponse(status=204)
        return HttpResponse(status=401 if not user.is_authenticated else 403)
    if rel.startswith("dokumen/"):
        from dokumen.models import Dokumen, DokumenRevisi
        terbuka = DokumenRevisi.objects.filter(
            file=rel, dokumen__status=Dokumen.Status.FINAL,
            dokumen__status_akses=Dokumen.StatusAkses.TERBUKA,
        ).exists()
        if terbuka:
            return HttpResponse(status=204)
    if user.is_authenticated and user.is_active:
        return HttpResponse(status=204)
    return HttpResponse(status=401)
