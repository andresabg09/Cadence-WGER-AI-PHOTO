"""Web Push (RFC 8030 + RFC 8291 aes128gcm encryption + RFC 8292 VAPID) with `cryptography` and httpx only:
the usual helper packages need a compiler step that could break the Docker build."""

import base64
import json
import os
import struct
import time
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _point(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    public = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def generate_vapid_keys() -> tuple[str, str]:
    """(private key as base64url of its 32 bytes, public key as base64url of the 65-byte point)."""
    key = ec.generate_private_key(ec.SECP256R1())
    return b64u(key.private_numbers().private_value.to_bytes(32, "big")), b64u(_point(key))


def _private_from(raw: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(b64u_decode(raw), "big"), ec.SECP256R1())


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: bytes | None = None,
            sender_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """The body of a push message for one subscription (single record, RFC 8291)."""
    ua_public = b64u_decode(p256dh)
    auth_secret = b64u_decode(auth)
    sender = sender_key or ec.generate_private_key(ec.SECP256R1())
    sender_public = _point(sender)
    shared = sender.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))
    prk = HKDF(hashes.SHA256(), 32, salt=auth_secret, info=b"WebPush: info\x00" + ua_public + sender_public).derive(shared)
    salt = salt or os.urandom(16)
    cek = HKDF(hashes.SHA256(), 16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(prk)
    nonce = HKDF(hashes.SHA256(), 12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(prk)
    sealed = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # 0x02 = last (and only) record
    return salt + struct.pack(">I", 4096) + bytes([len(sender_public)]) + sender_public + sealed


def vapid_headers(endpoint: str, private_raw: str, public_b64: str, subject: str) -> dict[str, str]:
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": subject}
    signing = f"{b64u(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())}." \
              f"{b64u(json.dumps(claims, separators=(',', ':')).encode())}"
    r, s = decode_dss_signature(_private_from(private_raw).sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
    token = f"{signing}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return {"Authorization": f"vapid t={token}, k={public_b64}"}


class Gone(Exception):
    """The push service says this subscription no longer exists (uninstalled app, revoked permission)."""


def send(subscription: dict, message: dict, private_raw: str, public_b64: str, subject: str) -> None:
    keys = subscription["keys"]
    body = encrypt(json.dumps(message).encode(), keys["p256dh"], keys["auth"])
    headers = {**vapid_headers(subscription["endpoint"], private_raw, public_b64, subject),
               "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": "3600", "Urgency": "normal"}
    response = httpx.post(subscription["endpoint"], content=body, headers=headers, timeout=15)
    if response.status_code in (404, 410):
        raise Gone(subscription["endpoint"])
    response.raise_for_status()
