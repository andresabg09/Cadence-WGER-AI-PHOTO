#!/usr/bin/env python3
"""Listener de webhook generico para despliegue automatico al hacer push.

Diseno para reutilizarse en cualquier servidor (este proyecto, el de Odoo,
otros futuros): solo usa la libreria estandar de Python, sin dependencias
externas, y todo su comportamiento se configura por variables de entorno.

Flujo en cada push recibido:
  1. Verifica la firma HMAC-SHA256 de GitHub (X-Hub-Signature-256).
  2. Verifica que el push sea a la rama configurada (DEPLOY_BRANCH).
  3. Responde 202 de inmediato y hace el trabajo pesado en un hilo aparte,
     para no hacer esperar a GitHub (que da por caido el webhook a los 10s).
  4. git fetch + git reset --hard origin/<branch> sobre REPO_PATH.
  5. Verifica que el hash local tras el pull coincida con el "after" que
     mando GitHub en el payload (si no coincide, aborta sin reiniciar nada).
  6. Corre `docker compose up -d --build` (o `restart` sobre
     COMPOSE_SERVICES si se especifica) para levantar el codigo nuevo.

Variables de entorno:
  WEBHOOK_SECRET     (obligatoria) - el mismo secreto configurado en GitHub.
  REPO_PATH          (obligatoria) - ruta absoluta del checkout git en el host.
  DEPLOY_BRANCH      (default: master)
  COMPOSE_SERVICES   (default: vacio = redeploy de todo el stack).
                     Lista separada por espacios para reiniciar solo esos
                     servicios en vez de todo el compose, ej: "cadence".
  WEBHOOK_PORT       (default: 9000)
  WEBHOOK_PATH       (default: /webhook)

Uso: correr como servicio systemd (ver deploy/cadence-webhook.service.example)
en el host que tiene acceso al docker socket y al checkout git, NO dentro de
un contenedor sin acceso a esas dos cosas.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("webhook")

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
REPO_PATH = os.environ["REPO_PATH"]
DEPLOY_BRANCH = os.environ.get("DEPLOY_BRANCH", "master")
COMPOSE_SERVICES = os.environ.get("COMPOSE_SERVICES", "").split()
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")


def verify_signature(payload: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    log.info("$ %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        log.info(result.stdout.strip())
    if result.stderr:
        log.info(result.stderr.strip())
    return result


def deploy(expected_after_sha: str) -> None:
    fetch = run(["git", "fetch", "origin", DEPLOY_BRANCH], cwd=REPO_PATH)
    if fetch.returncode != 0:
        log.error("git fetch fallo, abortando deploy")
        return

    reset = run(["git", "reset", "--hard", f"origin/{DEPLOY_BRANCH}"], cwd=REPO_PATH)
    if reset.returncode != 0:
        log.error("git reset fallo, abortando deploy")
        return

    local_sha = run(["git", "rev-parse", "HEAD"], cwd=REPO_PATH).stdout.strip()
    if local_sha != expected_after_sha:
        log.error(
            "Hash local (%s) no coincide con el hash del push (%s). "
            "Abortando reinicio de servicios por seguridad.",
            local_sha,
            expected_after_sha,
        )
        return

    log.info("Codigo actualizado y verificado en %s", local_sha)

    if COMPOSE_SERVICES:
        run(["docker", "compose", "up", "-d", "--build", *COMPOSE_SERVICES], cwd=REPO_PATH)
    else:
        run(["docker", "compose", "up", "-d", "--build"], cwd=REPO_PATH)

    log.info("Deploy completado")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - matches base signature
        log.info("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, b"ok")
        else:
            self._respond(404, b"not found")

    def do_POST(self):
        if self.path != WEBHOOK_PATH:
            self._respond(404, b"not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if not verify_signature(body, self.headers.get("X-Hub-Signature-256")):
            log.warning("Firma invalida, ignorando request")
            self._respond(401, b"invalid signature")
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, b"invalid payload")
            return

        ref = payload.get("ref", "")
        if ref != f"refs/heads/{DEPLOY_BRANCH}":
            log.info("Push a %s ignorado (esperando %s)", ref, DEPLOY_BRANCH)
            self._respond(200, b"ignored: different branch")
            return

        after_sha = payload.get("after", "")
        self._respond(202, b"deploy started")
        threading.Thread(target=deploy, args=(after_sha,), daemon=True).start()

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", WEBHOOK_PORT), Handler)
    log.info(
        "Escuchando en :%d%s para pushes a '%s' en %s",
        WEBHOOK_PORT,
        WEBHOOK_PATH,
        DEPLOY_BRANCH,
        REPO_PATH,
    )
    server.serve_forever()
