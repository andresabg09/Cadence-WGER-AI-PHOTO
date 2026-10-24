# cadence - contexto del proyecto

Lee este archivo completo antes de tocar nada. Es el reemplazo del prompt
largo que Andrés pegaba al inicio de cada chat nuevo - si estas leyendo esto
en una sesion de Claude Code, ya tienes el contexto completo.

## Quien es Andrés y por que existe este proyecto

Andrés es administrador tecnico unico de sus propios proyectos (Shalom
Panama y AutomatePTY). Este es un proyecto de uso personal: una extension
sobre **wger** (tracker de nutricion/ejercicio open-source, self-hosted)
para agregarle **reconocimiento automatico de comida por foto usando IA**,
algo que wger no trae de fabrica.

Andrés trabaja la mayor parte del tiempo en la calle. Por eso el requisito
de despliegue es "cero pasos manuales despues del push" (ver seccion de
despliegue).

**Rol de quien asista en este proyecto:** actuar como coach tecnico ademas
de ejecutor. Si algo que Andrés propone no es buena practica, decirlo
directamente con el porque, no asumir que toda idea es correcta.

## Decision de arquitectura: un solo repositorio

El plan original consideraba dos repos separados (uno de infraestructura,
`docker`, y uno nuevo llamado `cadence` para la app). Se descarto por un
bloqueo real: la integracion de GitHub de Claude Code no tiene permisos de
administracion para crear repositorios nuevos via API (`403 Resource not
accessible by integration`). Andrés decidio explicitamente fusionar todo
en este fork (`andresabg09/docker`) y renombrarlo a `cadence` en GitHub
(Settings -> Repository name - un cambio que solo el puede hacer, no
rompe URLs viejas porque GitHub redirige automaticamente).

**Regla que mantiene esto seguro:** todo el codigo propio de cadence vive
aislado en `cadence/` y `deploy/`. Los archivos que pertenecen al fork
original de wger (`docker-compose.yml`, `config/`, `services/`, etc.) solo
se tocan cuando es estrictamente necesario (ej. el fix de nginx descrito
abajo), para poder seguir haciendo `git pull` desde `wger-project/docker`
sin conflictos grandes.

## Estado de la infraestructura de wger (ya resuelto)

- **Repo:** este mismo (`andresabg09/docker`, fork de `wger-project/docker`).
- **Servicio en EasyPanel (Google Cloud):** proyecto `crm`, servicio tipo
  "Compose" llamado `wger`, fuente Git apuntando a este repo, rama `master`,
  `docker-compose.yml` en la raiz.
- **Dominio:** `https://crm-wger.cjauws.easypanel.host/`
- **Cambios ya aplicados sobre el compose oficial de wger:**
  1. Se quito `ports: - "80:80"` de nginx (el puerto 80 del host lo maneja
     EasyPanel para todos los proyectos, incluyendo Odoo de Shalom Panama).
  2. Se elimino el servicio `powersync` completo (stub, `depends_on`,
     `include`) - es sincronizacion offline para apps moviles, no aplica
     aqui, y sin su configuracion (usuario `powersync_storage` sin crear en
     Postgres) causaba un bucle de reinicio.
  3. **Bug encontrado y corregido en esta sesion:** el punto 2 solo se
     habia aplicado en `docker-compose.yml`. `config/nginx.conf` seguia
     teniendo el `upstream powersync { server powersync:8080; }` y el
     `location /ps/` que lo usaba - con el contenedor `powersync` ya
     eliminado, nginx fallaba al arrancar con
     `host not found in upstream "powersync"`. Ya esta corregido.
  4. Quedan huerfanos sin usar (no se borraron, no hacen dano): 
     `services/powersync.yaml` y `services/config-powersync/*.yaml` (no
     estan en el `include:` del compose, asi que nunca se levantan).
- **Nota de arquitectura (Docker Swarm/EasyPanel):** cuando se quita un
  servicio del compose, el contenedor viejo puede quedar huerfano. Si se
  quita otro servicio en el futuro, verificar con `docker ps -a | grep
  <nombre>` por SSH.
- **Pendiente de confirmar (requiere acceso SSH/EasyPanel que este
  asistente no tiene):** que tras el fix de `nginx.conf`, el stack completo
  (`web`, `nginx`, `db`, `cache`, `celery_worker`, `celery_beat`) quede
  arriba sin reinicios, y que el dominio cargue el login de wger.

## La app cadence (carpeta `cadence/`)

Servicio FastAPI separado que consume la API REST de wger - **no modifica
el core de wger**. Flujo funcional:

1. Usuario sube/captura una foto de un plato.
2. Gemini Flash (`GEMINI_MODEL`, variante Lite) identifica cada componente
   del plato por separado (ej. "pollo", "arroz", "ensalada"), nunca calorias
   ni cantidades - eso siempre sale de wger.
3. Por cada componente, se busca en `/api/v2/ingredient/search/` de wger y
   se re-rankea localmente con fuzzy matching (`rapidfuzz`) para mostrar
   2-3 candidatos.
4. El usuario confirma con un toque cual es el correcto (y el gramaje).
5. Se crea el registro via `POST /api/v2/nutritiondiary/` de wger.

**Sin probar contra la instancia real todavia** - no hay acceso de red
desde este entorno hacia `crm-wger.cjauws.easypanel.host`, asi que los
nombres exactos de campos de `/api/v2/nutritiondiary/` y
`/api/v2/ingredient/search/` estan implementados segun el esquema conocido
de wger, pero **hay que verificarlos con la instancia real** (`GET
/api/v2/nutritiondiary/` con un token valido, o revisando la Swagger UI en
`/api/v2/` de esa instancia) antes de dar por bueno el flujo de confirmacion.

Estructura:

```
cadence/
  app/
    main.py          - endpoints FastAPI: /health, / (camera.html), /api/analyze, /api/confirm
    config.py        - settings desde env (.env)
    vision.py        - cliente de Gemini, prompt que prohibe calcular calorias
    wger_client.py   - cliente de la API de wger (search, crear diary entry)
    matching.py      - fuzzy matching con rapidfuzz (con tests)
    schemas.py       - modelos pydantic
  static/            - PWA: index/scan/confirm/search.html + css/pulse.css + js/{api,shell,theme,install}.js
  tests/             - tests de matching.py (pasan: `pytest cadence/tests`)
  requirements.txt, Dockerfile, .env.example
```

Integrado en el `docker-compose.yml` raiz como servicio `cadence` (build
desde `./cadence`, expone 8001 interno). Expuesto publicamente en
`https://crm-wger.cjauws.easypanel.host/cadence/` via un `location
/cadence/` en `config/nginx.conf` que usa el resolver DNS de Docker en vez
de un `upstream` estatico - a proposito, para no repetir el bug de
powersync si el contenedor `cadence` tarda en levantar o falla el build.

**Importante:** `env_file` de `cadence` en el compose usa `required: false`
- si `cadence/.env` no existe todavia, el stack completo debe poder seguir
arrancando (wger incluido). El servicio `cadence` simplemente respondera
errores 500 claros ("GEMINI_API_KEY no esta configurado", etc.) hasta que
se configure `cadence/.env` a partir de `cadence/.env.example`.

**Ruta con slash final obligatoria:** `/cadence/` (con slash). Ya hay un
`location = /cadence { return 301 /cadence/; }` para el caso sin slash.

**Dos trampas ya resueltas (no reintroducir):**
- En `config/nginx.conf`, `proxy_pass http://$var/;` (con variable) NO quita el
  prefijo `/cadence/`: manda todo a `/` del upstream. Se usa `rewrite ^/cadence/(.*)$ /$1 break;`
  + `proxy_pass http://$cadence_upstream;`.
- La hora de cada registro se interpreta en `TIMEZONE` (default `America/Panama`),
  no en el reloj del contenedor (UTC); si no, desayuno cae en "almuerzo" y todo
  lo posterior a las 7pm cuenta como "manana".

## Interfaz de camara (requisito de diseno)

`cadence/static/camera.html` implementa guia en tiempo real (no es una
foto a ciegas): usa `DeviceOrientationEvent` para medir la inclinacion del
telefono y da retroalimentacion en vivo ("baja el angulo", "acercate",
"angulo correcto - captura ahora") apuntando a ~45 grados respecto al
plato (ni cenital ni al ras), porque ese angulo da mas informacion de
volumen a la IA. Pide permiso de sensor explicitamente en iOS 13+.

Consideraciones de diseno de la categoria (investigacion de mercado, no
reabrir debate salvo problema real de precision):

- La estimacion de porcion/volumen es el mayor error, no la identificacion
  del alimento. 10-35% de margen es normal incluso en apps lideres - no
  perseguir precision perfecta ahi.
- Segmentar por componentes, no por plato completo (ya implementado en
  `vision.py`: el prompt exige listar cada componente por separado).
- Nunca tratar el resultado de la IA como final - la confirmacion del
  usuario es central al flujo (ya implementado: `/api/analyze` devuelve
  candidatos, no crea nada hasta `/api/confirm`).

## Despliegue automatico (`deploy/`)

Decision final: push a `master` -> webhook liviano en el servidor -> git
pull + verificacion de hash + rebuild + restart, sin pasos manuales de
Andrés (ni siquiera SSH de una linea). Implementado en
`deploy/webhook_listener.py` - un solo archivo de libreria estandar de
Python, configurable por variables de entorno, pensado para copiarse tal
cual a otros servidores de Andrés (ej. el de Odoo de Shalom Panama).

**Antes de activarlo en este proyecto especifico**, leer la advertencia en
`deploy/README.md` sobre como esto interactua con el propio mecanismo de
deploy de EasyPanel (que ya administra su propio checkout de este repo).

Los commits y push a este repo **solo se ejecutan con confirmacion
explicita de Andrés** en cada ocasion - nunca de forma automatica.

## Rebranding wger -> cadence (pendiente, ultimo paso)

Requisito: ninguna referencia visible a "Wger" en la interfaz final (marca,
logo, titulo de pestana, footer, emails) - todo reemplazado por "cadence".
Es un requisito de implementacion real sobre wger mismo (frontend,
templates, config, textos), no solo del servicio `cadence/`. **Todavia no
se ha hecho.** wger no expone una variable de entorno de "nombre de sitio"
en `config/prod.env` (se reviso y no existe `SITE_NAME`/`SITE_LOGO`) - hay
que decidir el enfoque (sub_filter en nginx para texto, override de
assets estaticos para el logo, o tocar templates de wger) en una sesion
dedicada, evaluando el riesgo de romper el core de wger. El resto del
lenguaje visual (paleta, tipografia, iconografia Material Symbols de MUI)
se mantiene igual - es un rebranding de marca, no un rediseno.

## Principio: wger es el almacen, cadence es la unica cara

Cadence guarda diario, metas, peso y racha en wger via su API REST, y usa su catalogo de
alimentos. Unica excepcion (25 oct 2026): un almacen SQLite minimo propio (`cadence/app/store.py`,
volumen Docker `cadence-data` montado en `/data`, `DATA_DIR`) para lo que wger no puede guardar:
la observacion de cada registro y las fotos (foto del plato 1280 px + recorte nitido por
ingrediente). NO duplica diario ni alimentos. Si se borra el volumen se pierden notas y fotos, no
el diario. Endpoints: `PUT /api/diary/{id}/note`, `POST /api/entry-media`, `GET /api/media/...`. Andres NO debe tener que entrar a la interfaz de wger
para nada: todo lo que wger exija (plan de nutricion, etc.) lo crea cadence solo
(`create_nutrition_plan`). Unicos pasos de servidor, una sola vez: cargar el catalogo
(`sync-ingredients-bulk`) y generar el token. Si algun dia se quiere independizar del todo,
la alternativa es base propia en cadence + wger solo como catalogo (reescritura mayor,
decision de Andres; no hecha).

## Plan por bloques (fuente de verdad del avance)

Mockup aprobado: artifact "cadence — Diseño" (claude.ai/artifact/VtU9UcFoBkUS7g7Nry3Exc),
15 pantallas de celular + (desde el Bloque 1) versiones tablet y escritorio.
Cada bloque se construye COMPLETO, se prueba (tests + navegador con wger simulado),
se publica a `master` y se valida con UNA sola revision en el servidor
(`/cadence/api/diagnostics?deep=1`). No se entrega a medias ni bug por bug.

- **Bloque 0 - Destrabar y verificar (HECHO, 24 oct 2026).** `/api/diagnostics?deep=1` todo
  verde en produccion: token, Gemini, plan (lo crea cadence), diario, busqueda y registro de
  prueba. Catalogo cargado con `cadence/scripts/load_ingredients.py` (~49 mil alimentos
  genericos en/es; el comando oficial `sync-ingredients-bulk` es demasiado lento aqui).
  Pendiente de pulir: ranking de `/api/search` (hoy devuelve las primeras coincidencias de
  wger sin ordenar por parecido) y aumentar el limite de busqueda antes de rankear.
- **Bloque 1 - Responsive tablet y escritorio (HECHO).** Breakpoints 600/1024 en
  `static/css/pulse.css`; barra lateral en escritorio via `static/js/shell.js`
  (`<body class="with-shell" data-page="...">`); escritorio: escaneo = subir foto/webcam
  (sin sensor), confirmar con foto + total en la columna derecha; tablet: 2 columnas.
- **Bloque 2 - Flujo central real (HECHO salvo la prueba con foto real).** Comida elegible
  al registrar (`meal` -> `datetime_for_meal`), imagen reducida antes de subir, estados
  (sin conexion con cola offline en localStorage, wger no responde con "Reintentar", diario
  vacio, "no logramos identificar el plato"), iconos PNG + hoja "Instalar app"
  (`static/js/install.js`), `/api/wger-status`, `/api/meal-now`, y el diagnostico profundo
  (`/api/diagnostics?deep=1`) crea y borra un registro de prueba en wger. Pendiente: probar
  con una foto real y ajustar campos de wger si el diagnostico lo pide.
  Prueba de campo 1 (24 oct): primera foto real (helados) -> arreglado: icono de apariencia
  invisible en oscuro (los `<button>` no heredan `color`), icono de instalar descentrado,
  porciones iniciales (la IA estima gramos en `estimated_grams`; solo punto de partida),
  ranking de candidatos (trae 100 de wger y puntua `WRatio + ratio`), miniaturas con la foto
  del usuario (localStorage, `cadence_thumbs`), y errores 500 ahora dicen la causa en vez de
  quedar en blanco (`/api/today` ya no cae si el plan o un alimento no se pueden leer).
  Fotos por ingrediente (24 oct): la IA devuelve `box_2d` por componente (0-1000, convertido a
  `box=[x,y,w,h]` 0-1); la pantalla Confirmar muestra la(s) foto(s) arriba con cada zona
  numerada, y cada ingrediente lleva su recorte con zoom (`cropThumb` en api.js, sessionStorage
  `cadence_photos`, cada componente con `photo`+`box`). "Agregar otra foto" (`scan.html?append=1`)
  suma fotos a un mismo registro. El diario guarda el recorte de cada entrada (localStorage).
  Sin `box` valido se usa la foto entera. Pendiente de validar con cajas reales de Gemini.
  Comida segun la hora de la foto (24 oct): el selector Desayuno/Almuerzo/Merienda/Cena es
  SIEMPRE libre; solo se preselecciona una sugerencia con la hora de la foto (EXIF
  DateTimeOriginal de las fotos de galeria, `readTakenAt` en api.js; camara de la app = ahora;
  sin EXIF = fecha del archivo). `ConfirmRequest.taken_at` fecha el registro en el DIA de la foto
  y, si el usuario elige otra comida, dentro de la ventana de esa comida (`datetime_for_meal`).
  Una hora futura se recorta a "ahora". `/api/meal-now?at=` devuelve la sugerencia.
  Alimentos "como se comen" (24 oct): el catalogo de wger (Open Food Facts) es de productos
  CRUDOS/de supermercado ("White Rice" = 340 kcal, cocido = 130). `cadence/scripts/seed_staples.py`
  agrega ~60 basicos preparados en en/es (source_name=`cadence`, valores tipo USDA); la busqueda
  los trae siempre (`candidate_pool`), les da +20 puntos, muestra el gemelo en/es una sola vez en
  el idioma del usuario, y el prompt pide `search_name` "tal como se come" (cooked/grilled).
  Prueba de campo 2 (24 oct): el guardado SI funcionaba; las fotos viejas se registran en su dia
  (la del 10 oct) y el diario solo mostraba hoy. Ahora: flechas/selector de dia en el diario
  (`/api/today?date=`), al guardar se abre el dia del plato con aviso "Guardado en ...", tocar un
  registro abre su detalle (foto del plato con la zona, macros, cantidad y comida editables via
  `PATCH /api/diary/{id}`, observacion, borrar). Observaciones, recortes y fotos viven en
  almacen del servidor (ver Principio; wger no tiene campo de nota ni fotos). Lo que quedo en
  localStorage de versiones anteriores (`cadence_notes`, `cadence_thumbs`, `cadence_plates`) sube
  solo al servidor al abrir el dia (`syncLocalExtras`). Calidad: la foto de trabajo es 1280 px q0.88
  y el recorte sale de ella (420 px al guardar), con zoom/lightbox en el detalle. La barra inferior tapaba/era tapada
  por las filas (`.tab-bar` sin z-index): corregido. Avisos (toast) ahora opacos + caja de error fija.
  Calendario con fueguitos (25 oct): tocar el dia del diario abre un calendario propio
  (`openCalendar` en index.html, `GET /api/calendar?month=`); cada dia con registros lleva una llama
  con su racha (dias seguidos que terminan ese dia; tras un hueco vuelve a 1). Color por racha:
  1-2 ambar, 3-6 naranja, 7-13 rojo, 14-29 magenta con brillo, 30+ violeta con brillo. La racha que
  entra al mes se calcula leyendo hacia atras hasta que se rompe (`streak_by_day` en meals.py).
  Regla de la racha (25 oct, decision de Andres): subir una foto vieja NO recupera ni extiende la
  racha. Solo cuenta un dia si algo se registro ESE mismo dia. `entry_meta.logged_on` (store.py)
  guarda el dia real de registro de cada entrada al confirmar; `counts_for_streak` (meals.py)
  descarta las que se registraron despues de su fecha (las anteriores a esta regla se aceptan).
  El calendario marca esos dias con un punto gris (hay datos, sin llama) y al guardar un registro
  tardio sale el aviso "no suma a tu racha". Tambien rige la racha de la cabecera.
- **Bloque 3 - Datos personales.** Perfil, Objetivos (Mifflin-St Jeor, guarda goal_* del
  plan), Progreso (racha, peso desde weightentry, logros), Historial.
- **Bloque 4 - Ajustes y habitos.** Ajustes (hub), Apariencia (toggle ya hecho),
  Bienvenida, Recordatorios, registro por voz.
- **Bloque 5 - Integraciones wger.** Puente de entrenamiento (workoutsession/workoutlog),
  codigo de barras, alimento personalizado.
- **Bloque 6 - Marca y deploy.** Rebranding wger -> cadence; decidir deploy automatico
  (ver `deploy/README.md`).

## Reglas de trabajo (validas para cualquier chat futuro)

- Codigo quirurgico y cambios minimos sobre reescrituras amplias.
- Publicacion: Andrés autorizo (octubre 2026) que cada bloque se haga completo y se
  publique a `master` al terminar, sin pedir confirmacion por cada arreglo. Ramas
  `fix/...` solo si hay riesgo de romper el deploy. Nunca poner claves en el repo.
- Antes de pedirle algo a Andrés, agrupar TODO lo que necesita hacer en un solo mensaje
  (el no puede iterar bug por bug: cada deploy le cuesta ~5 min).
- Nunca reabrir la decision de Gemini Flash Lite como modelo de vision
  salvo problema real de precision en pruebas.
- Las calorias siempre salen de la base de datos de wger, nunca las
  calcula el modelo de vision.
