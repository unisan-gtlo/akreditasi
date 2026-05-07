"""Factory untuk dispatch ke resolver yang tepat berdasarkan jenis_data.

Usage:
    from master_akreditasi.data_resolvers import get_resolver
    
    resolver = get_resolver(mapping.jenis_data)
    summary = resolver.get_dosen_summary(sesi, dtps, mapping)
"""
from .base import BaseDataResolver


# Registry: jenis_data -> resolver class
# Diisi via register_resolver() saat module load.
# Lazy registration menghindari circular imports antar resolver files.
_REGISTRY: dict[str, type[BaseDataResolver]] = {}


def register_resolver(resolver_cls: type[BaseDataResolver]) -> type[BaseDataResolver]:
    """Register resolver class ke registry.

    Bisa dipakai sebagai decorator atau manual call.
    Resolver class harus punya `jenis_data` non-empty.

    Usage as decorator:
        @register_resolver
        class BKDResolver(BaseDataResolver):
            jenis_data = 'BKD'
            ...
    """
    if not resolver_cls.jenis_data:
        raise ValueError(
            f"Resolver {resolver_cls.__name__} harus punya jenis_data non-empty."
        )
    if resolver_cls.jenis_data in _REGISTRY:
        existing = _REGISTRY[resolver_cls.jenis_data].__name__
        raise ValueError(
            f"jenis_data='{resolver_cls.jenis_data}' sudah terdaftar oleh "
            f"{existing}. Tidak bisa double-register dengan {resolver_cls.__name__}."
        )
    _REGISTRY[resolver_cls.jenis_data] = resolver_cls
    return resolver_cls


def get_resolver(jenis_data: str) -> BaseDataResolver:
    """Dispatch ke resolver instance yang cocok dengan jenis_data.

    Args:
        jenis_data: salah satu nilai ButirDataDosenMapping.JENIS_DATA_CHOICES.

    Returns:
        Instance resolver siap pakai.

    Raises:
        UnsupportedJenisDataError: kalau jenis_data tidak punya resolver terdaftar.
    """
    if jenis_data not in _REGISTRY:
        registered = sorted(_REGISTRY.keys())
        raise UnsupportedJenisDataError(
            f"Tidak ada resolver untuk jenis_data='{jenis_data}'. "
            f"Yang tersedia: {registered}"
        )
    return _REGISTRY[jenis_data]()


def list_supported_jenis_data() -> list[str]:
    """Return list jenis_data yang punya resolver terdaftar."""
    return sorted(_REGISTRY.keys())


class UnsupportedJenisDataError(Exception):
    """Raised saat get_resolver dipanggil dengan jenis_data yang belum punya resolver."""
    pass