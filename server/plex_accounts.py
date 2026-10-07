"""Authenticated encryption binds each Plex token to its Pig Music account."""

import base64
import json
import os
import tempfile
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from .security import secret_file
from .lifecycle import coordinated
from .library import load_json


class PlexAccounts:
    def __init__(self, store):
        self.store = store
        self.key = HKDF(secret_file(store.directory), 32, b"pig-music-plex-v1", SHA256)

    def encrypt(self, user_id, token):
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=os.urandom(12))
        cipher.update(user_id.encode())
        ciphertext, tag = cipher.encrypt_and_digest(token.encode())
        return base64.b64encode(cipher.nonce + tag + ciphertext).decode()

    def token(self, user_id):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT token_encrypted FROM plex_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
        if not row:
            return None
        raw = base64.b64decode(row[0], validate=True)
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=raw[:12])
        cipher.update(user_id.encode())
        return cipher.decrypt_and_verify(raw[28:], raw[12:28]).decode()

    @coordinated
    def set(self, user_id, token, label):
        if not token or len(token) > 512 or any(ord(c) < 33 for c in token):
            raise ValueError("Enter a valid Plex token.")
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO plex_accounts VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET token_encrypted=excluded.token_encrypted,plex_user_label=excluded.plex_user_label",
                (user_id, self.encrypt(user_id, token), label[:128]),
            )
        return {"configured": True, "label": label[:128]}

    def status(self, user_id):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT plex_user_label FROM plex_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
        return {"configured": bool(row), "label": row[0] if row else None}

    @coordinated
    def migrate_owner(self):
        path = self.store.directory / "plex-connection.json"
        config = load_json(path)
        if not config.get("token"):
            return
        with self.store.connect() as conn:
            owner = conn.execute("SELECT id FROM users WHERE role='owner'").fetchone()
            if not owner:
                return
            conn.execute(
                "INSERT OR IGNORE INTO plex_accounts VALUES (?,?,?)",
                (
                    owner[0],
                    self.encrypt(owner[0], config["token"]),
                    "Existing Plex account",
                ),
            )
        config.pop("token", None)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.store.directory, prefix=".plex-config-", delete=False
        ) as stream:
            json.dump(config, stream)
            temporary = stream.name
        try:
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
