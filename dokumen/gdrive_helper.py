"""
Google Drive URL parser & validator.

Support format URL:
  - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
  - https://drive.google.com/file/d/FILE_ID/view
  - https://drive.google.com/open?id=FILE_ID
  - https://docs.google.com/document/d/FILE_ID/edit
  - https://docs.google.com/spreadsheets/d/FILE_ID/edit
  - https://docs.google.com/presentation/d/FILE_ID/edit
"""
import re
import urllib.parse
import urllib.request
from urllib.error import URLError


# =========================================================
# URL PARSER
# =========================================================

# Regex patterns untuk extract file_id
GDRIVE_PATTERNS = [
    r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
    r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)",
    r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
    r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)",
    r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)",
    r"drive\.google\.com/uc\?id=([a-zA-Z0-9_-]+)",
]

VALID_HOSTS = ["drive.google.com", "docs.google.com"]


def extract_gdrive_file_id(url):
    """
    Extract file_id dari URL Google Drive.
    Return (file_id, error_message).
    """
    if not url:
        return None, "URL kosong"

    url = url.strip()

    # Basic URL validation
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None, "URL tidak valid"

    if parsed.scheme not in ("http", "https"):
        return None, "URL harus dimulai dengan http:// atau https://"

    if parsed.netloc not in VALID_HOSTS:
        return None, (
            f"URL harus dari Google Drive ({', '.join(VALID_HOSTS)}). "
            f"Domain Anda: {parsed.netloc}"
        )

    # Try each pattern
    for pattern in GDRIVE_PATTERNS:
        match = re.search(pattern, url)
        if match:
            file_id = match.group(1)
            if len(file_id) >= 20:  # GDrive IDs biasanya 25+ char
                return file_id, None

    return None, (
        "Format URL Google Drive tidak dikenali. Pastikan URL-nya seperti: "
        "https://drive.google.com/file/d/XXXXXXXXX/view"
    )


def build_preview_url(file_id):
    """Return URL untuk embed preview iframe."""
    return f"https://drive.google.com/file/d/{file_id}/preview"


def build_download_url(file_id):
    """Return URL untuk download langsung."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# =========================================================
# LINK VALIDATOR (best effort)
# =========================================================

def check_link_accessible(url, timeout=5):
    """
    Cek apakah URL bisa diakses publik (tanpa login).
    Return (is_accessible, message).
    
    Note: best-effort only. Google Drive bisa return 200 bahkan untuk file yang
    sebenarnya private, tapi untuk format download URL kita bisa deteksi.
    """
    if not url:
        return False, "URL kosong"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (SIAKRED Link Validator)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")

            if status == 200:
                # Kalau response adalah HTML Google Drive login page, berarti private
                if "text/html" in content_type:
                    body = resp.read(2048).decode("utf-8", errors="ignore")
                    if "accounts.google.com" in body.lower() or "sign in" in body.lower():
                        return False, "Link privat — butuh login Google. Set sharing ke 'Anyone with the link'"
                return True, "Link accessible"
            else:
                return False, f"HTTP status {status}"
    except URLError as e:
        return False, f"Tidak bisa akses URL: {str(e.reason)[:100]}"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def validate_gdrive_url(url):
    """
    Validasi URL Google Drive end-to-end:
    1. Extract file_id
    2. Optional: ping preview URL
    
    Return dict: {is_valid, file_id, preview_url, download_url, warning}
    """
    file_id, err = extract_gdrive_file_id(url)
    if err:
        return {
            "is_valid": False,
            "file_id": None,
            "error": err,
        }

    preview_url = build_preview_url(file_id)

    # Best-effort check (non-blocking, kalau gagal tetap lanjut dengan warning)
    accessible, msg = check_link_accessible(preview_url, timeout=5)

    return {
        "is_valid": True,
        "file_id": file_id,
        "preview_url": preview_url,
        "download_url": build_download_url(file_id),
        "accessible": accessible,
        "warning": None if accessible else msg,
    }