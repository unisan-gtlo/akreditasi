"""
Django signals untuk integrasi dosen-akreditasi.

Yang ditangani di sini:

  1. post_save SesiAkreditasi (created=True)
     → Auto-populate DTPSDosenSesi dengan dosen homebase prodi.

CARA REGISTER:
  Tambahkan di master_akreditasi/apps.py method ready():

      class MasterAkreditasiConfig(AppConfig):
          name = 'master_akreditasi'

          def ready(self):
              from . import signals  # noqa: F401
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='sesi.SesiAkreditasi')
def auto_populate_dtps_on_sesi_create(sender, instance, created, **kwargs):
    """Auto-populate DTPS pool saat sesi akreditasi baru dibuat.

    Hanya trigger saat created=True (bukan saat update).
    Tidak fail kalau ada error — error di-log agar sesi tetap bisa dibuat.
    """
    if not created:
        return

    try:
        from .simda_dosen import auto_populate_dtps_homebase

        # Coba ambil user dari instance kalau ada
        user = getattr(instance, 'dibuat_oleh', None)

        created_count = auto_populate_dtps_homebase(instance, user=user)
        logger.info(
            "Auto-populated %d DTPS records for sesi %s (prodi=%s)",
            created_count, instance.id, instance.kode_prodi,
        )
    except Exception as exc:
        # Sesi tetap dibuat meski auto-populate gagal — operator bisa retry manual
        logger.exception(
            "Failed to auto-populate DTPS for sesi %s: %s",
            instance.id, exc,
        )
