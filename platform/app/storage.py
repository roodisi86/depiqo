"""Document storage. Files live outside the web root under random names and are only
served through an authorised route. Types are checked on content, not on the file name."""
import hashlib
import os
import secrets

from flask import current_app

from . import db
from .util import now_iso

ALLOWED = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
KINDS = {"contract": "Huurcontract", "inspection": "Plaatsbeschrijving of opleverrapport", "photo": "Foto",
         "quote": "Offerte of factuur", "agreement": "Getekend akkoord", "court": "Vonnis",
         "bankbewijs": "Bankbewijs van ontvangst", "blokkering": "Blokkeringsattest of bewijs e-DEPO",
         "vrijgave": "Bewijs van vrijgave of terugbetaling", "other": "Overig"}


class UploadError(Exception):
    pass


def detect_mime(head):
    for mime, magics in ALLOWED.items():
        if any(head.startswith(m) for m in magics):
            return mime
    return None


def save_upload(file_storage, deposit, kind, uploaded_by_kind, user_id):
    if kind not in KINDS:
        raise UploadError("Kies het soort document.")
    if not file_storage or not file_storage.filename:
        raise UploadError("Kies een bestand.")
    data = file_storage.read(current_app.config["MAX_UPLOAD_BYTES"] + 1)
    if len(data) > current_app.config["MAX_UPLOAD_BYTES"]:
        raise UploadError("Het bestand is groter dan 10 MB.")
    if not data:
        raise UploadError("Het bestand is leeg.")
    mime = detect_mime(data[:16])
    if not mime:
        raise UploadError("Alleen PDF, JPG en PNG zijn toegestaan.")
    stored = secrets.token_hex(16)
    path = os.path.join(current_app.config["STORAGE_DIR"], stored)
    with open(path, "wb") as f:
        f.write(data)
    name = os.path.basename(file_storage.filename).replace("\x00", "")[:120] or "document"
    return db.run("INSERT INTO documents (org_id, deposit_id, uploaded_by_kind, uploaded_by, kind, filename, stored_name, mime, size_bytes, sha256, created_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (deposit["org_id"], deposit["id"], uploaded_by_kind, user_id, kind, name, stored, mime, len(data),
                   hashlib.sha256(data).hexdigest(), now_iso()))


def file_path(doc):
    return os.path.join(current_app.config["STORAGE_DIR"], doc["stored_name"])
