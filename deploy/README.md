# Webhook de despliegue automatico

Escucha pushes a GitHub y hace `git pull` + rebuild + reinicio del servicio
correspondiente sin intervencion manual. Es un solo archivo de la libreria
estandar de Python (`webhook_listener.py`), sin dependencias externas, para
poder copiarlo tal cual a otro servidor (por ejemplo, el de Odoo de Shalom
Panama) cambiando solo variables de entorno.

## Advertencia importante sobre EasyPanel

Este proyecto (`wger` + `cadence`) esta desplegado como un servicio "Compose"
dentro de **EasyPanel**, que ya administra su propio checkout de este
repositorio y su propio ciclo de `git pull` + `docker compose up` cuando
detectas cambios o le das "Deploy" manualmente. **Antes de montar este
webhook sobre ese mismo checkout**, confirma una de estas dos rutas:

1. **Mas simple para este proyecto:** revisa si tu servicio en EasyPanel
   tiene una opcion de "Auto Deploy" / webhook nativo de GitHub. Si la
   tiene, actıvala y evitas mantener infraestructura extra para este caso.
   Este script de todas formas sirve como la receta reutilizable para el
   servidor de Odoo, que no corre EasyPanel.
2. **Si prefieres el webhook propio para este proyecto tambien:** debe
   correr en el host (no dentro de un contenedor sin acceso al socket de
   Docker) y `REPO_PATH` debe apuntar exactamente al mismo checkout que usa
   EasyPanel para este servicio, para no terminar con dos copias del repo
   desincronizadas. Verifica esa ruta con EasyPanel antes de activarlo.

## Como funciona

1. GitHub manda un POST a `/webhook` en cada push, firmado con HMAC-SHA256
   usando un secreto compartido.
2. El script verifica la firma y que el push sea a la rama configurada.
3. Responde 202 de inmediato (GitHub da por caido el webhook a los 10s) y
   hace el trabajo pesado en un hilo aparte.
4. `git fetch` + `git reset --hard origin/<rama>` sobre `REPO_PATH`.
5. Compara el hash local resultante contra el `after` que mando GitHub en
   el payload del push - si no coinciden, aborta sin tocar los contenedores.
6. `docker compose up -d --build` (todo el stack, o solo los servicios de
   `COMPOSE_SERVICES` si se especifica) para levantar el codigo nuevo.

`git reset --hard` descarta cualquier cambio no commiteado en el checkout
del servidor - es el comportamiento esperado para un directorio de
despliegue, pero no lo uses sobre un checkout donde tambien editas a mano.

## Variables de entorno

| Variable            | Obligatoria | Default    | Descripcion |
|---------------------|-------------|------------|-------------|
| `WEBHOOK_SECRET`    | si          | -          | Debe coincidir con el secreto configurado en GitHub |
| `REPO_PATH`         | si          | -          | Ruta absoluta del checkout git en el host |
| `DEPLOY_BRANCH`     | no          | `master`   | Rama que dispara el deploy |
| `COMPOSE_SERVICES`  | no          | (vacio)    | Servicios a reiniciar, separados por espacio. Vacio = todo el stack |
| `WEBHOOK_PORT`      | no          | `9000`     | Puerto donde escucha |
| `WEBHOOK_PATH`      | no          | `/webhook` | Path del endpoint |

## Puesta en marcha (en el servidor, por SSH)

```bash
# 1. Generar un secreto random
openssl rand -hex 32

# 2. Copiar el service file de ejemplo y editar rutas/secreto
sudo cp deploy/cadence-webhook.service.example /etc/systemd/system/cadence-webhook.service
sudo nano /etc/systemd/system/cadence-webhook.service

# 3. Habilitar y arrancar
sudo systemctl daemon-reload
sudo systemctl enable --now cadence-webhook

# 4. Verificar que responde
curl http://localhost:9000/health
```

## Configurar el webhook en GitHub

En el repositorio -> Settings -> Webhooks -> Add webhook:

- **Payload URL:** `https://tu-dominio-o-ip:9000/webhook` (necesitas exponer
  ese puerto o ponerlo detras de un reverse proxy con esa ruta).
- **Content type:** `application/json`
- **Secret:** el mismo valor de `WEBHOOK_SECRET`
- **Which events:** solo "Just the push event"

## Reutilizarlo en otro servidor (ej. Odoo)

Copia unicamente `webhook_listener.py` y el `.service.example`, ajusta
`REPO_PATH`, `DEPLOY_BRANCH` y `COMPOSE_SERVICES` (o adapta el comando final
de `deploy()` si ese servidor no usa `docker compose`), genera un secreto
nuevo y repite los pasos de arriba. No depende de nada especifico de wger
ni de cadence.
