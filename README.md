# cadence

Proyecto personal de Andrés: despliegue de [wger](https://wger.de/)
(tracker de nutricion/ejercicio open-source) mas una extension propia de
reconocimiento de comida por foto usando IA (carpeta `cadence/`). Este repo
es un fork de `wger-project/docker` - contiene tanto la infraestructura de
wger sin modificar su core, como el codigo propio de cadence, aislado en
sus propias carpetas para poder seguir sincronizando con el upstream.

**Si vas a trabajar en este repo (humano o IA), lee primero
[`CLAUDE.md`](./CLAUDE.md)** - tiene todo el contexto del proyecto, las
decisiones ya tomadas y el porque, para no tener que reexplicar nada desde
cero en cada sesion nueva.

## Estructura

- `docker-compose.yml`, `config/`, `services/`, `dev*/` - stack de wger tal
  como viene de `wger-project/docker`, con ajustes minimos documentados en
  `CLAUDE.md` (sin `powersync`, nginx sin puerto publicado).
- `cadence/` - el servicio propio: reconocimiento de comida por foto
  (Gemini Flash) + integracion con la API de wger. Ver
  [`cadence/README.md`](./cadence/README.md).
- `deploy/` - webhook liviano de despliegue automatico (push a `master` ->
  pull + rebuild + restart, sin pasos manuales). Ver
  [`deploy/README.md`](./deploy/README.md).

## docker compose stacks para wger (upstream, sin cambios de fondo)
Contains 3 docker compose environments:

* prod (in root of this repository)
* dev (uses sqlite)
* dev-postgres (uses postgresql)

The production Docker Compose file initializes a production environment with the
application server, a reverse proxy, a database, a caching server, and a Celery
queue, all configured. Data is persisted in volumes, if you want to use folders,
read the warning in the env file.

**TLDR:** 

1. clone this whole repository: `git clone https://github.com/wger-project/docker.git`
1. start the containers: `docker compose up -d` 
1. setup offline mode storage: `docker compose exec web ./manage.py setup-powersync-storage`

For more details, consult the documentation (and the config files):

* production: <https://wger.readthedocs.io/en/latest/installation/docker.html>
* development: <https://wger.readthedocs.io/en/latest/development/docker.html>

It is recommended to regularly pull the latest version of this repository
(`git pull`), since sometimes new configurations, environmental variables or
service files are added.

## Contact

Feel free to contact us if you found this useful or if there was something that
didn't behave as you expected. We can't fix what we don't know about, so please
report liberally. If you're not sure if something is a bug or not, feel free to
file a bug anyway.

* Mastodon: <https://fosstodon.org/@wger>
* Discord: <https://discord.gg/rPWFv6W>
* Issue tracker: <https://github.com/wger-project/docker/issues>


## Sources

All the code and the content is freely available:

* <https://github.com/wger-project/>

## Licence

The application is licenced under the Affero GNU General Public License 3 or
later (AGPL 3+).



