"""
Kompres foto profil yang sudah diunggah (rektor, dekan, kaprodi, user).

Foto diperkecil ke sisi terpanjang --max-size px dan disimpan ulang sebagai
WebP (transparansi tetap terjaga). File asli disimpan sebagai <nama>.orig.
Contoh foto rektor: PNG 228 KB -> WebP 14 KB.

Pakai:
    python manage.py optimize_profile_images --dry-run
    python manage.py optimize_profile_images
"""
import os
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand

from core.models import FakultasProfile, ProdiProfile, SiteProfile, User

TARGETS = [
    (SiteProfile, "foto_rektor"),
    (FakultasProfile, "foto_dekan"),
    (ProdiProfile, "foto_kaprodi"),
    (User, "foto_profil"),
]


class Command(BaseCommand):
    help = "Perkecil & kompres foto profil di MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Hanya tampilkan, tidak mengubah file.")
        parser.add_argument("--max-size", type=int, default=800, help="Sisi terpanjang (px). Default 800.")
        parser.add_argument("--min-kb", type=int, default=120, help="Lewati file di bawah ukuran ini (KB). Default 120.")

    def handle(self, *args, **opts):
        from PIL import Image

        dry_run = opts["dry_run"]
        max_size = opts["max_size"]
        min_bytes = opts["min_kb"] * 1024
        total_before = total_after = 0

        for model, field in TARGETS:
            for obj in model.objects.exclude(**{f"{field}": ""}).exclude(**{f"{field}__isnull": True}):
                image_field = getattr(obj, field)
                try:
                    path = Path(image_field.path)
                except Exception:
                    continue
                if not path.exists() or path.stat().st_size < min_bytes:
                    continue

                before = path.stat().st_size
                new_path = path.with_suffix(".webp")
                if dry_run:
                    self.stdout.write(f"[dry-run] {model.__name__}#{obj.pk} {path.name} ({before // 1024} KB) -> {new_path.name}")
                    continue

                backup = path.with_name(path.name + ".orig")
                if not backup.exists():
                    shutil.copy2(path, backup)
                tmp_path = new_path.with_name(new_path.name + ".tmp")
                with Image.open(path) as im:
                    im.thumbnail((max_size, max_size), Image.LANCZOS)
                    if im.mode not in ("RGB", "RGBA"):
                        im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "P") else "RGB")
                    # WebP: dukung transparansi, jauh lebih kecil dari PNG/JPEG
                    im.save(tmp_path, format="WEBP", quality=85, method=6)

                os.replace(tmp_path, new_path)
                if new_path != path:
                    path.unlink()
                    rel = os.path.relpath(new_path, Path(image_field.storage.location)).replace(os.sep, "/")
                    model.objects.filter(pk=obj.pk).update(**{field: rel})

                after = new_path.stat().st_size
                total_before += before
                total_after += after
                self.stdout.write(f"{model.__name__}#{obj.pk} {path.name}: {before // 1024} KB -> {new_path.name}: {after // 1024} KB")

        if not dry_run and total_before:
            self.stdout.write(self.style.SUCCESS(f"Total: {total_before // 1024} KB -> {total_after // 1024} KB"))
