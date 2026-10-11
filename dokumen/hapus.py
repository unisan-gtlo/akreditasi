"""
Hapus dokumen permanen (superadmin / pemilik dokumen), dengan pengaman:
- ditolak bila dokumen masih ditautkan ke butir (lepas tautan dulu);
- ditolak bila dokumen FINAL masih menjadi bukti di sesi akreditasi, KECUALI ada
  dokumen FINAL lain dengan file/tautan yang sama (berarti ini duplikat).
Dokumen yang tidak boleh dihapus tetap bisa diarsipkan (Edit Metadata → Diarsipkan).
"""
import logging

from django.db import transaction

from .models import Dokumen, DokumenRevisi
from .permissions import can_edit_dokumen

audit = logging.getLogger("siakred.audit")


def kembaran(dok):
    """Dokumen FINAL lain yang file/tautan aktifnya sama persis (duplikat)."""
    rev = dok.revisi.filter(aktif=True).first()
    if not rev:
        return []
    q = {"file_hash": rev.file_hash} if rev.file_hash else ({"gdrive_url": rev.gdrive_url} if rev.gdrive_url else None)
    if not q:
        return []
    ids = (DokumenRevisi.objects.filter(aktif=True, dokumen__status="FINAL", **q)
           .exclude(dokumen=dok).values_list("dokumen_id", flat=True))
    return list(Dokumen.objects.filter(pk__in=list(ids)))


def sesi_pemakai(dok):
    """Sesi akreditasi yang menghitung dokumen ini sebagai bukti."""
    if dok.status != "FINAL" or not dok.butir_dokumen_id:
        return []
    from master_akreditasi.models import ButirDokumen
    from sesi.models import SesiAkreditasi
    from .sharing import butir_groups, sesi_dokumen_qs

    grup = butir_groups([dok.butir_dokumen])[dok.butir_dokumen_id]
    instrumen = set(ButirDokumen.objects.filter(pk__in=grup).values_list("sub_standar__standar__instrumen_id", flat=True))
    hasil = []
    for s in SesiAkreditasi.objects.filter(instrumen_id__in=instrumen).exclude(status="DIBATALKAN"):
        if sesi_dokumen_qs(s, grup).filter(pk=dok.pk).exists():
            hasil.append(s)
    return hasil


def cek_hapus(user, dok):
    """Return (boleh, [alasan penolakan], info dict)."""
    alasan = []
    if not can_edit_dokumen(user, dok)[0]:
        alasan.append("Hanya Super Admin atau pemilik dokumen (unit yang sama) yang bisa menghapus.")
    n_tautan = dok.tautan_butir.count()
    if n_tautan:
        alasan.append(f"Dokumen masih ditautkan ke {n_tautan} butir. Lepas tautannya dulu di panel 'Dipakai untuk butir lain'.")
    duplikat = kembaran(dok)
    sesi = sesi_pemakai(dok)
    if sesi and not duplikat:
        daftar = ", ".join(f"#{s.pk} {s.kode_prodi or ''}".strip() for s in sesi[:5])
        alasan.append(f"Dokumen masih menjadi bukti di sesi akreditasi ({daftar}). "
                      f"Bila tidak dipakai lagi, arsipkan saja (Edit Metadata → Status: Diarsipkan).")
    return (not alasan), alasan, {"duplikat": duplikat, "sesi": sesi, "n_revisi": dok.revisi.count()}


def hapus_dokumen(user, dok):
    """Hapus dokumen + revisi + log/verifikasi (cascade) dan file lokalnya setelah commit."""
    berkas = [r.file.name for r in dok.revisi.all() if r.file]
    ringkas = f"#{dok.pk} '{dok.judul}' ({dok.scope_label}, butir {dok.butir_dokumen.kode if dok.butir_dokumen_id else 'Pustaka'})"
    with transaction.atomic():
        dok.delete()

        def _hapus_berkas():
            from django.core.files.storage import default_storage
            for nama in berkas:
                try:
                    default_storage.delete(nama)
                except Exception:
                    audit.warning("Gagal menghapus berkas %s", nama)

        transaction.on_commit(_hapus_berkas)
    audit.warning("Dokumen dihapus permanen oleh %s: %s, %d berkas", user.username, ringkas, len(berkas))
    return ringkas
