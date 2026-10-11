"""
Navigasi "Kembali ke posisi sebelumnya".

Halaman asal menambahkan ?next=<path asal> pada tautan ke halaman detail ({% url_next %}),
halaman detail meneruskannya ke halaman turunan ({% url_teruskan %}), dan tombol Kembali
memakai {% asal_navigasi %}. Posisi gulir & bagian yang terbuka dipulihkan oleh JS di
layouts/internal.html (tautan berkelas js-kembali).
"""
from urllib.parse import quote, urlencode

from django import template
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

register = template.Library()

_LABEL = [
    ("/dokumen/pustaka", "Pustaka Dokumen"),
    ("/dokumen/butir/", "Butir Dokumen"),
    ("/dokumen/verifikasi", "Verifikasi Dokumen"),
    ("/dokumen/dokumen/", "Detail Dokumen"),
    ("/master/sinkron", "Pusat Sinkronisasi"),
    ("/laporan", "Laporan"),
    ("/dokumen/", "Dokumen Saya"),
]


def next_aman(request):
    """Nilai ?next= yang aman (path lokal) atau ''."""
    if request is None:
        return ""
    n = request.GET.get("next", "") or request.POST.get("next", "")
    if n and n.startswith("/") and url_has_allowed_host_and_scheme(n, allowed_hosts=set()):
        return n
    return ""


def dengan_next(url, nxt):
    if not nxt:
        return url
    return f"{url}{'&' if '?' in url else '?'}{urlencode({'next': nxt})}"


def label_untuk(path):
    if "/bundle" in path:
        return "Bundle Sesi"
    if path.startswith("/sesi/"):
        return "Sesi Akreditasi"
    for awal, label in _LABEL:
        if path.startswith(awal):
            return label
    return "Halaman sebelumnya"


@register.simple_tag(takes_context=True)
def url_next(context, viewname, *args):
    """URL ke viewname dengan ?next=<halaman ini> (path + query)."""
    req = context.get("request")
    return dengan_next(reverse(viewname, args=args), req.get_full_path() if req else "")


@register.simple_tag(takes_context=True)
def next_ini(context):
    """'?next=<halaman ini>' untuk tautan yang ditulis manual (mis. /dokumen/dokumen/5/)."""
    req = context.get("request")
    return "?next=" + quote(req.get_full_path(), safe="") if req else ""


@register.simple_tag(takes_context=True)
def url_teruskan(context, viewname, *args):
    """URL ke viewname sambil meneruskan ?next= yang sedang berlaku (bukan halaman ini)."""
    return dengan_next(reverse(viewname, args=args), next_aman(context.get("request")))


@register.simple_tag(takes_context=True)
def asal_navigasi(context, default_url="", default_label="Kembali"):
    """{'url', 'label'} tujuan tombol Kembali: ?next= bila ada, selain itu default."""
    n = next_aman(context.get("request"))
    if n:
        return {"url": n, "label": label_untuk(n.split("?")[0])}
    return {"url": default_url, "label": default_label}
