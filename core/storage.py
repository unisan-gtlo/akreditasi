"""
Storage static files SIAKRED.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SiakredStaticStorage(CompressedManifestStaticFilesStorage):
    """Static ber-hash + gzip/brotli dari WhiteNoise.

    File yang tidak ada di manifest (lupa collectstatic / path typo) tetap
    dirender dengan nama aslinya, bukan error 500 di seluruh halaman.
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            return name
