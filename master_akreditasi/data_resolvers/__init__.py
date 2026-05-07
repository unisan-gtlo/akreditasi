"""Data Resolver — Strategy Pattern untuk fetch & render data dosen dari SIMDA.

Setiap jenis_data di ButirDataDosenMapping (BKD, PENDIDIKAN, JABFUNG, PROFIL)
punya resolver-nya sendiri. View tinggal panggil get_resolver(jenis_data) tanpa
peduli jenis spesifiknya.

Public API:
    get_resolver(jenis_data) -> BaseDataResolver instance
    list_supported_jenis_data() -> list[str]
    BaseDataResolver, DosenSummary -> untuk type hints
    UnsupportedJenisDataError -> raised saat jenis_data tidak ada resolver-nya
"""
from .base import BaseDataResolver, DosenSummary
from .factory import (
    get_resolver,
    list_supported_jenis_data,
    register_resolver,
    UnsupportedJenisDataError,
)

# Import resolver modules untuk memastikan @register_resolver decorator dijalankan
# saat package ini di-import (auto-registration pattern).
from . import bkd_resolver  # noqa: F401
from . import pendidikan_resolver  # noqa: F401

__all__ = [
    'BaseDataResolver',
    'DosenSummary',
    'get_resolver',
    'list_supported_jenis_data',
    'register_resolver',
    'UnsupportedJenisDataError',
]