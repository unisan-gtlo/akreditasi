"""
Invalidasi cache otomatis saat data berubah.

Catatan: QuerySet.update()/bulk_create() tidak memicu signal. Data yang
berubah lewat jalur itu ikut basi paling lama sebesar TTL cache-nya
(lihat core/cache_utils.py), atau panggil invalidate_*() secara manual.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache_utils import (
    invalidate_notif,
    invalidate_publik,
    invalidate_sidebar_stats,
    invalidate_verif,
)

MASTER_MODELS = [
    'master_akreditasi.Instrumen',
    'master_akreditasi.Standar',
    'master_akreditasi.SubStandar',
    'master_akreditasi.ButirDokumen',
    'master_akreditasi.MappingProdiInstrumen',
]
VERIF_MODELS = [
    'dokumen.Dokumen',
    'dokumen.DokumenRevisi',
    'dokumen.VerifikasiDokumen',
]
PUBLIK_MODELS = [
    'dokumen.Dokumen',
    'sesi.SesiAkreditasi',
    'core.FakultasTheme',
]


def _on_master_change(sender, **kwargs):
    invalidate_sidebar_stats()
    invalidate_publik()


def _on_verif_change(sender, **kwargs):
    invalidate_verif()


def _on_publik_change(sender, **kwargs):
    invalidate_publik()


for _model in MASTER_MODELS:
    post_save.connect(_on_master_change, sender=_model, dispatch_uid=f'cache_master_save_{_model}')
    post_delete.connect(_on_master_change, sender=_model, dispatch_uid=f'cache_master_del_{_model}')

for _model in VERIF_MODELS:
    post_save.connect(_on_verif_change, sender=_model, dispatch_uid=f'cache_verif_save_{_model}')
    post_delete.connect(_on_verif_change, sender=_model, dispatch_uid=f'cache_verif_del_{_model}')

for _model in PUBLIK_MODELS:
    post_save.connect(_on_publik_change, sender=_model, dispatch_uid=f'cache_publik_save_{_model}')
    post_delete.connect(_on_publik_change, sender=_model, dispatch_uid=f'cache_publik_del_{_model}')


@receiver(post_save, sender='core.Notifikasi', dispatch_uid='cache_notif_save')
@receiver(post_delete, sender='core.Notifikasi', dispatch_uid='cache_notif_del')
def _on_notifikasi_change(sender, instance, **kwargs):
    invalidate_notif(instance.penerima_id)
