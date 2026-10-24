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

## Cuentas multiusuario (decision de Andres, 25 oct 2026)

cadence se va a dar a mas personas (y quiza a alquilar o vender): NADIE debe pasar por el registro
de wger. Diseno:
- **Cuentas propias de cadence** en el almacen SQLite (`app/store.py`: users, sessions, invites,
  weights, usage): correo + contrasena (scrypt), cookie de sesion `cadence_session` (HttpOnly,
  SameSite=Lax, 60 dias). Sin SMTP: el administrador crea codigos de invitacion de un solo uso y
  restablece contrasenas desde Perfil: genera un CODIGO de un solo uso (24 h) que la persona escribe en el login ("Tengo un codigo", `POST /api/auth/reset`) para elegir su nueva clave; su clave actual sigue valiendo hasta entonces. El PRIMER registro es el administrador (y con `ADMIN_EMAIL`
  solo ese correo puede crearlo). `OPEN_REGISTRATION=true` abre el registro sin codigo.
- **Una sola cuenta de wger (el token de servicio) y UN PLAN DE NUTRICION POR PERSONA** (descripcion
  `cadence:<id>`, `plan_for` en main.py). El administrador adopta el plan anterior a las cuentas
  (`find_legacy_plan_id`). wger no ve usuarios. Metas, perfil, peso, notas y fotos viven en
  cadence (wger no tiene donde guardarlos por persona).
- **Aislamiento (lo mas importante):** todo endpoint de datos depende de `current_user`; el plan
  sale SIEMPRE del usuario, nunca del cliente (`plan_id` del request se ignora); todo cambio/borrado
  de un registro pasa por `owns_entry` (dueno guardado en `entry_meta.user_id` o plan de wger);
  las fotos se sirven solo a su dueno. Cubierto por `tests/test_accounts.py`: AL AGREGAR UN ENDPOINT
  NUEVO, exigir `current_user` y verificar la propiedad, y agregar su prueba de aislamiento.
- **Costo de IA:** `ANALYZE_DAILY_LIMIT` (40 fotos/dia por persona; el admin no tiene limite).
- **Primer uso:** `login.html` (entrar / crear cuenta con codigo, `?invite=CODIGO`), `onboarding.html`
  (sexo, fecha de nacimiento, estatura, peso, actividad, objetivo -> meta calculada con
  Mifflin-St Jeor en `app/nutrition.py`, ajustable de 50 en 50 kcal; guardas de seguridad: minimos
  de kcal, menores de 18 sin deficit, peso bajo no baja). Pocas opciones a la vez: lo demas se va
  mostrando de a poco. `profile.html` = Perfil (quien eres: nombre, peso, plan, actividad) y
  `settings.html` = Ajustes (SEPARADOS por decision de Andres: Instalar app, apariencia, recordatorios, cuenta,
  invitaciones y personas para el admin, cerrar sesion); `goals.html` = Objetivos.
- Fechas: usar `pickDate()` (js/datepicker.js), nunca `<input type="date">` (se ve viejo y su icono es ilegible en oscuro). `color-scheme` sigue al tema.
- Pantallas de pantalla completa (scan) se fijan a `--app-h` (= innerHeight real): en la app instalada `100dvh` puede ser mayor que lo visible y tapaba el boton de captura.
- Al cambiar de persona en un dispositivo se borran sus caches locales (`rememberUser`).
- Pendiente para vender/alquilar: terminos y privacidad reales, recuperacion de contrasena por correo,
  respaldo del volumen `cadence-data`, y revisar AGPL de wger si se modifica su codigo (rebranding).

## Plan por bloques (fuente de verdad del avance)

Mockup aprobado: artifact "cadence — Diseño" (claude.ai/artifact/VtU9UcFoBkUS7g7Nry3Exc),
Reorganizado el 25 oct 2026 en cuatro paginas: Celular, Tablet, Escritorio (diseno FINAL de todas las pantallas, incluidos los bloques 8-12)
y Pruebas (los cambios nuevos se prueban primero ahi, en una copia, y solo al aprobarse se aplican a las tres). No volver a crear tableros
"Plan N" ni duplicados de tablet/escritorio: se edita el tablero final.
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
  Panel de rachas (25 oct): la pastilla del fueguito de la cabecera es un boton (`openStreaks`,
  `GET /api/streaks`): racha actual con sus dias (cada llama crece segun el dia de la racha),
  mejor racha y rachas anteriores (ultimos 12 meses); tocar un dia/racha abre ese dia.
- **Bloque 3 - Datos personales (HECHO).** Perfil, Objetivos (Mifflin-St Jeor; las metas viven en
  cadence, no en wger), registrar peso, cuentas y bienvenida/cuestionario (ver "Cuentas
  multiusuario"), racha + calendario + panel de rachas, navegar por dias. Progreso (`progress.html`,
  `GET /api/progress`: racha, ultimas 4 semanas, grafica de peso con meta, 12 logros calculados en
  `app/progress.py`, sin guardarlos) e Historial (`history.html`, `GET /api/history`: dias con kcal y
  fotos, "ver dias anteriores"). Peso: `GET /api/weights`, `POST /api/weight`, `DELETE /api/weight/{dia}`.
- **Bloque 4 - Ajustes y habitos (HECHO).** Hub de Ajustes (dentro de `profile.html`), Apariencia,
  Instalar app, Bienvenida, Recordatorios y Registro por voz. Recordatorios (`reminders.html`,
  `app/reminders.py`): avisos push de agua (cada 1-4 h entre dos horas), comidas (desayuno/almuerzo/cena
  a su hora; NO avisa si esa comida ya esta registrada) y resumen semanal (domingos). Web Push propio en
  `app/webpush.py` (cifrado RFC 8291 verificado contra el vector oficial + VAPID, solo `cryptography` y
  httpx: `pywebpush` necesita compilar `http-ece` y podria romper el build). Claves VAPID se generan solas
  y viven en la tabla `kv`. Programador: hilo que despierta cada minuto (`start_scheduler`, evento
  startup); cada aviso sale una vez por persona/dia (`claim_reminder`) y solo dentro de los 30 min
  siguientes a su hora. En iPhone solo funciona con la app INSTALADA. Voz (`voice.html`, `POST
  /api/voice`): graba, convierte a WAV 16 kHz en el navegador y Gemini lo convierte en la misma lista de
  componentes que una foto (con gramos si los dijo) -> Confirmar. Cuenta para el limite diario de
  analisis. NO verificado aun en un telefono real: push (ver "Enviar aviso de prueba" en Recordatorios).
- **Bloque 5 - Integraciones (HECHO, con una decision).** El catalogo de wger es SOLO LECTURA por API
  (`IngredientViewSet` es ReadOnly): no se pueden crear alimentos ahi. Por eso los alimentos propios
  y los productos escaneados viven en cadence (`custom_foods`, id de ingrediente NEGATIVO) y sus
  registros en `local_entries` (id `c<n>`); `user_entries()` en main.py junta wger + locales y TODO lo
  que lee el diario (hoy, calendario, rachas, progreso, historial, recientes) pasa por ahi. Codigo de
  barras (el lector SOLO lee codigos de barras EAN/UPC/Code128, no QR; si ninguna base lo conoce, la hoja explica el motivo con `reason`: not_listed | no_nutrition | unreachable): `GET /api/barcode/{codigo}` = alimento propio -> wger (`ingredientinfo?code=`, wger consulta
  Open Food Facts por su cuenta) -> Open Food Facts directo -> hoja para crearlo; lector en
  `static/js/barcode.js` (BarcodeDetector o ZXing local en `js/vendor/`, Apache-2.0). Alimento
  personalizado: `static/js/food-sheet.js`, `POST /api/foods`. Entrenamiento: NO se usa
  workoutsession de wger (es de una sola cuenta de servicio, no por persona): registro propio
  (`workouts`, `POST/DELETE /api/workouts`), kcal quemadas ESTIMADAS (MET x peso x horas) y no
  cambian la meta del dia.
- (Decision de Andres, 24 oct 2026: los Bloques 6 y 7 se POSPONEN; por ahora lo usan el y su novia. NO implementarlos hasta que lo pida.)
- **Bloque 6 - Marca y deploy.** FALTA TODO: rebranding wger -> cadence (ademas, algunos mensajes de
  error del servidor aun nombran a wger), decidir deploy automatico (ver `deploy/README.md`).
- **Bloque 7 - Listo para otras personas (propuesto, antes de abrir a desconocidos).** FALTA TODO:
  terminos y privacidad reales, recuperacion de contrasena por correo (requiere SMTP: lo aporta
  Andres), respaldo del volumen `cadence-data`, Ayuda y soporte, revisar AGPL de wger antes de vender.
- REGLA ANTI-REPETICION: antes de empezar un bloque, comparar este listado con el codigo real
  (grep de endpoints/paginas) y trabajar SOLO lo que dice FALTA; al terminar, mover lo hecho a
  HECHO en este mismo listado y subirlo en el mismo commit.

## Bloques propuestos 8-12: ideas de otra app (PLAN, NO IMPLEMENTAR hasta que Andres diga "go")

Origen (25 oct 2026): Andres mando capturas de otra app de nutricion con cosas que le gustaron: puntuacion nutricional con
premios hexagonales, niveles de proteina y fibra, agua con vasos, retos con monedas, buscador de entrenamientos y plan de
comidas. Los disenos viven en el canvas "cadence - Diseno" (tableros "Plan 8-12 ..."); Andres los aprueba o descarta ANTES de
tocar codigo. Reglas para todos estos bloques: las calorias y macros salen SIEMPRE de wger/alimentos propios (la IA nunca
calcula; las puntuaciones se calculan en el servidor con formulas fijas y visibles); todo dato por persona vive en el servidor
(nada solo en localStorage); tablas nuevas con `CREATE TABLE IF NOT EXISTS` (sin pasos manuales en el servidor); lecturas con
`apiGetSWR`; hojas con `pushOverlay`; recompensas con `sfx.play`; cada endpoint nuevo exige `current_user` + prueba de
aislamiento; probar con Playwright y wger simulado. Nada de candados ni "premium": todo se desbloquea. No copiar: ayuno,
fotos de stock, tienda de monedas con dinero.
- **Bloque 8 - Puntuacion nutricional y niveles (HECHO, 25 oct 2026; aprobado por Andres).** Implementado en `app/scoring.py` (formulas fijas: macros 30, proteina 20, fibra 15, azucar+grasa saturada 15, variedad 10, porcion 10; un criterio sin datos (menos del 60 % del peso del plato) NO resta y se avisa en `partial`; tabla de basicos con fibra/azucar/grasa sat. en `STAPLE_EXTRA`), `GET /api/today` devuelve `score`/`levels` por comida y del dia (promedio ponderado por kcal), hoja `static/js/meal-detail.js` (se abre tocando la pastilla de puntaje de cada comida) y ayudas de dibujo en `static/js/bits.js`. Los alimentos propios aceptan fibra opcional. Texto original del plan: `app/scoring.py`: puntaje 0-100 por comida y por dia
  (Excelente/Buena/Regular/Mejorable) con formula visible ("Como se calcula"): balance de macros frente a la meta de la persona,
  proteina de la comida frente a su parte del dia, fibra, azucar y grasa saturada, variedad y porcion. Si falta un dato (wger no
  siempre trae fibra/azucar) NO penaliza y avisa "datos parciales". Barras "Nivel de proteina" y "Nivel de fibra" con marcador.
  Hay que leer `fibres`, `carbohydrates_sugar`, `fat_saturated`, `sodium` de `ingredientinfo` (verificar en la instancia real) y
  agregar fibra opcional a los alimentos propios y a los basicos preparados (archivo de la app, sin pasos en el servidor).
  `GET /api/today` devuelve `score` por comida y del dia. Tamano M.
- **Bloque 9 - Inicio renovado (HECHO, 25 oct 2026).** Agua con vasos de 250 ml (`#glasses` en index.html; tocar un vaso llena o vacia hasta el; meta por persona en `water_goals`, automatica = 35 ml/kg en vasos de 250, `PUT /api/water/goal`, `/api/today` devuelve `water_goal_ml`), tarjetas de puntuacion del dia y de fibra, y el interruptor Restantes / Por quemar (`/api/today` devuelve `burn`: kcal sobre la meta menos lo que quemaron los entrenamientos, y minutos de un trote ligero de 7 MET; el modo se recuerda por dispositivo). Texto original del plan: Tarjetas: Agua con vasos de 250 ml (meta editable por persona, `water_goal_ml`; reemplaza la
  botella), Puntuacion del dia (anillo), "Calorias restantes / por quemar" (alterna; usa los entrenamientos), Fibra. Depende del 8. Tamano M.
- **Bloque 10 - Premios y Retos (HECHO, 25 oct 2026; monedas = opcion A, solo cosmeticos).** Logica pura en `app/gamify.py` (4 premios por comida + 18 hitos = 22 premios; 4 retos diarios y 6 semanales; la tienda tiene Tema Aurora, Tema Atardecer y Marco dorado), tablas `awards`, `coin_ledger` (una fila por reto y periodo: no se cobra dos veces) y `equipped`. Endpoints: `/api/awards`, `/api/challenges`, `POST /api/challenges/claim`, `POST /api/shop/buy|equip`; `/api/today` trae `awards` por comida y `awards_new`. Paginas `challenges.html` (Retos + tienda) y `awards.html` (Premios), pestana Retos en el celular (con punto si hay monedas por reclamar) y Perfil en la barra, items en la barra lateral. Los retos de calorias solo se cumplen entre 90 % y 115 % de la meta (nunca premian comer de menos). `me.themes` y `me.frame` llegan con el perfil; el tema comprado se usa por dispositivo (`themeCycle()` en theme.js). Texto original del plan: Premios hexagonales calculados de los datos (los 12 logros de `progress.py` + premios por comida)
  y guardados al desbloquearse (`awards`: persona, clave, dia). Retos diarios (4) y semanales (hasta 6) con progreso calculado
  (90 % de la meta, registrar 2 comidas, puntuacion mayor a 70, primera comida del dia; racha de 5 dias, agua 5 dias, registrar peso,
  3 entrenamientos), recompensa en monedas (`coin_ledger`, una vez por reto y periodo, se reclama con un toque). Pestana nueva "Retos".
  DECISION PENDIENTE de Andres: para que sirven las monedas (recomendado: solo cosmeticos: temas, sonidos, marcos de foto; NO
  escudos de racha, porque la racha ya no se recupera por decision suya). Los retos no pueden premiar comer de menos. Depende del 8. Tamano L.
- **Bloque 11 - Entrenamientos con buscador (HECHO, 25 oct 2026).** `nutrition.ACTIVITIES` (34 actividades con MET del Compendio; las claves antiguas siguen valiendo), `GET /api/activities` (kcal por minuto con tu peso), `POST/PATCH/DELETE /api/workouts` (hora `at` y edicion que recalcula), `static/js/workouts.js` (buscador, hoja con duraciones 15/30/60/otro, tocar un entrenamiento lo edita). Texto original del plan: Mas actividades (tabla MET ampliada en `nutrition.py`), lista con busqueda e
  iconos, hoja con kcal estimadas y kcal/min (MET x peso), duraciones 15/30/60/otra, hora y nota, editar y borrar. Sigue siendo
  estimacion y no cambia la meta. Independiente. Tamano S-M.
- **Bloque 12 - Ideas de comidas y favoritas (HECHO, 25 oct 2026).** `ideas.html` (ruta `/ideas.html`, item "Ideas de comidas" de la
  barra lateral y tarjeta "Ideas para completar tu dia" en Inicio solo hoy y con mas de 150 kcal por comer). `GET /api/favorites`
  (`_favorites` en main.py): agrupa los ultimos 60 dias por (dia, comida), la "receta" = conjunto de ingredientes; top 8 por veces y
  recencia, con la foto del plato de la persona si la hay (chip "TU FOTO"); "Repetir" = `POST /api/confirm` con la comida elegida.
  `GET /api/ideas?meal=&refresh=`: kcal/proteina que faltan = meta - lo comido hoy; si faltan < 120 kcal responde `done` sin llamar a
  Gemini. `vision.suggest_meals` (prompt: SOLO nombres y gramos, nunca calorias) -> cada ingrediente se busca con `match_components`
  (descarta los de parecido < 0.55; una idea con < 2 ingredientes resueltos se descarta) -> kcal/proteina de wger/alimentos propios ->
  ordenadas por cercania a lo que falta. Cuenta para `ANALYZE_DAILY_LIMIT` (admin libre); cache 30 min por persona/dia/comida/tramo.
  Sin fotos de stock: mosaico de color con la inicial. Fotos para las ideas ("comunidad"): idea futura, NO hecha. `apiGet` ahora usa
  `cache: 'no-store'` (al volver con Atras el navegador repetia la respuesta vieja del diario). Sin verificar con Gemini real.
- Orden sugerido: 8, 9, 11, 10, 12. Cada bloque se publica completo y por separado.

## Velocidad (25 oct 2026; mantener)

La app debe sentirse como app nativa. Reglas que la logran, no deshacerlas:
- `wger_client.py`: UN pool de conexiones por proceso (`_Http`), ruta INTERNA `WGER_INTERNAL_URL` (default
  `http://nginx` en el compose, con el Host publico) con respaldo automatico a `WGER_BASE_URL`; cache de
  alimentos 6 h (`get_ingredient`).
- `main.py`: `user_entries()` cachea 2 min la lectura del diario de wger; TODA escritura al diario debe llamar
  `invalidate_entries(user.id)`. Lecturas independientes en paralelo (alimentos del dia, trozos del ano).
- Navegador: `apiGetSWR()` (js/api.js) pinta el ultimo dato guardado al instante y lo reemplaza con el fresco;
  toda escritura exitosa limpia ese cache (`swrClear`). El service worker (`sw.js`, `__BUILD__` sellado por
  el servidor en cada deploy) abre paginas y scripts desde cache y los refresca detras; al desplegar una version
  nueva muestra "Hay una version nueva - Actualizar". Fuentes de Google sin bloquear el pintado; GZip activo.
- Pantallas nuevas: usar `apiGetSWR` para sus lecturas y no esperar a `ensureSession` antes de pedir datos.

## Boton central, sonidos, bienvenida y agua (25 oct 2026)

- **Boton central del diario** = la marca de cadence (NO una camara). Al tocarlo despliega Foto · Codigo · Voz
  (`#launcher` en index.html + CSS `.lc-*`); es una hoja encima: usa `pushOverlay/dismissOverlay`, y al elegir una
  opcion cierra primero y luego navega (asi el Atras desde la camara cae en un diario limpio). Diseno en el canvas
  "cadence - Diseno" (Inicio, Progreso, Tablet, "Menu + abierto", "Menu +: secuencia").
- **Sonidos** (`js/sfx.js`, sintetizados con WebAudio, sin archivos): `sfx.play('save'|'photo'|'water'|'goal'|'streak'|
  'themeDark'|...)`. Ajustes tiene interruptor y volumen (`cadence_sound`). Premian: guardar comida (campana), foto
  (obturador + campana), vaso de agua (gota), meta del dia y meta de agua (acorde), racha nueva (chispa mas aguda
  cuanto mas larga), cambiar tema. La pagina nueva no hereda el permiso de audio: por eso confirm.html espera ~420 ms
  antes de salir y las celebraciones de meta/racha se disparan en el diario (`celebrate()` en index.html, solo
  cuando se llega justo despues de guardar). Toda accion nueva con recompensa debe llamar `sfx.play`.
- **Bienvenida/entrada** (`onboarding.html` intro y `login.html`): `cadenceHero()` (el icono real de la app con
  anillos orbitales) + `mountConstellation(document.body)` (`js/constellation.js`): estrellas unidas por lineas; el
  cursor las arremolina, mantener presionado abre un agujero negro y soltar lanza una onda. Respeta
  `prefers-reduced-motion`.
- **Agua en fotos y voz**: la IA devuelve agua sola como `water_ml` (no es alimento; `split_water` en main.py,
  `AnalyzeResponse.water_ml`). confirm.html muestra la tarjeta "Agua detectada" (editable) y al confirmar suma los
  ml a la barra del dia de la foto (`addWater` -> `POST /api/water`) sin crear registro en el diario; si solo hay
  agua el boton dice "Sumar el agua".

## Registrar: un solo menu (25 oct 2026, decision de Andres)

- La CAMARA YA NO TIENE selector Foto/Codigo/Voz. La unica forma de elegir como registrar es el menu central:
  celular = `#launcher` (boton con la marca); computadora = `js/register-menu.js` (`openRegisterMenu({meal})`, boton
  "Registrar comida" de la barra lateral y "Registrar" del diario). `scan.html?mode=barcode` abre directo el modo
  codigo; `voice.html` es la voz.
- "Agregar desayuno/almuerzo/cena" (tarjetas punteadas del diario) NO abre la camara: abre ese mismo menu con la
  comida elegida (`openRegister(meal)`, chip "AGREGAR ALMUERZO"; los 3 enlaces llevan `?meal=`). "Agregar otro
  alimento al almuerzo" sigue yendo a la busqueda escrita (`search.html?meal=`), que se queda.
- Foto de perfil: `PUT/GET/DELETE /api/avatar` (tabla `avatars`, recorte cuadrado 360 px hecho en el navegador;
  `me.avatar_v` versiona la URL). Se pinta en Perfil, en la cabecera del diario y en la barra lateral (`paintAvatars`).
- Sonidos nuevos: `add` (anadir alimento), `pick` (elegir opcion), `streakOpen` (intro al abrir la racha).
- Sonidos al ir a Progreso / Retos / Premios (`navProgress|navChallenges|navAwards`): suenan al TOCAR el enlace (delegado en `sfx.js`, por `href`; la pagina abre ~340 ms despues, con un fundido) porque una pagina recien abierta casi nunca puede sonar (iPhone). Completos (empiezan, resuelven y se apagan solos en ~0.3 s: NO acortarlos ni recortar el retraso, que los cortaria). No usar `sfx.enter` para ellos.
- Agua: los vasos se construyen una vez y se actualizan en sitio (`renderWater`, index.html) para que el agua suba/baje; gota que cae, pop del vaso, oleaje y, al cumplir la meta, ola de saltos (CSS `.glass-btn.pour|drain|cheer`); el sonido llega con la gota (`WATER_LAND_MS`). Respeta `prefers-reduced-motion`.
- Sonidos de navegacion tambien: Historial (`navHistory`), Ideas (`navIdeas`) y volver al Diario (`navDiary`: flechas "Volver" y barra lateral; los flujos con `data-leave` quedan en silencio). El toque se retiene en la fase de captura y se reproduce tras `NAV_DELAY`, asi los manejadores propios de la pagina (`history.back()`) siguen funcionando. El boton Atras del sistema no puede sonar.
- Barra del dia (25 oct 2026, opcion B de Andres; `#dayBar`, `renderDayBar` en index.html, CSS `.day-bar`/`.db-*`): bajo el saludo y FIJA al hacer scroll (sticky): "Hoy · sabado 24 de octubre" (o Ayer / otro dia con su fecha), boton con el mes que abre el calendario de siempre, tira Lun-Dom con llama (racha) / punto gris (registrado tarde) / punto tenue (sin registro), flechas de semana y deslizar; tocar un dia = `goToDate` (sin historial nuevo). Fuera de hoy sale la franja "Estas viendo el ..., no hoy" + "Volver a hoy". Las llamas vienen de `/api/calendar` (cache propio `stripInfo`, no se borra en `loadToday`). En escritorio titulo y semana van en una sola fila. Reemplaza la barra "Hoy" que estaba sobre la lista de comidas y la fecha gris del saludo.
- Borrar un plato entero (25 oct 2026): en el diario, las fotos con 2+ alimentos tienen papelera en la foto y deslizar la foto a la izquierda ("Borrar plato"), con confirmacion; `POST /api/diary/bulk-delete {ids}` (todo o nada: si un id no es de la persona no se borra nada; prueba en `test_accounts.py`).
- Sonidos de llegada (`sfx.enter('enterProfile'|'enterSettings')`, una linea al inicio de cada pagina): cortos y
  bajitos; si el navegador no deja sonar en la pagina nueva se omiten (nunca se encolan para el primer toque) y no suenan al recargar.
- La foto ampliada del detalle (`openLightbox` en index.html) dibuja la zona azul del ingrediente sobre un marco (`.lb-frame`)
  que mide exactamente la foto, asi la zona sigue en su sitio al acercar.
- iOS: no hay WebKit en el entorno de pruebas, asi que NO esta probado en iPhone. Lo que se cuido por revision de
  codigo: `-webkit-backdrop-filter`, campos de 16 px (si no, iOS hace zoom), desbloqueo de audio en `click/touchend`,
  metas `apple-mobile-web-app-*`, push solo con la app instalada, lector de codigos con ZXing (sin BarcodeDetector).

## Agua (25 oct 2026, decision de Andres: nada de datos solo-en-el-navegador)

El agua se guarda POR PERSONA en el servidor (tabla `water_log`, `store.add_water` suma o resta ml de un dia en una sola
sentencia, asi dos dispositivos no se pisan; tope 10 000 ml/dia). `POST /api/water {date, add_ml}` y `/api/today` devuelve
`water_ml`. Offline: `addWater` (api.js) encola en `cadence_water_pending` y `flushWater` lo envia al volver. El agua que
versiones viejas dejaron en `localStorage` (`cadence_water_<dia>`) sube una sola vez con `POST /api/water/import` (se
queda con el mayor valor) y se borra del navegador. Regla general: nada que el usuario deba ver desde otro dispositivo puede
vivir solo en localStorage (solo caches, borradores y preferencias de ese aparato).

## Navegacion y boton Atras (regla de Andres, 25 oct 2026; aplica a TODA pantalla nueva)

cadence se usa como web y como app instalada (PWA en Android/iPhone). El boton Atras del sistema
(o del navegador) NUNCA debe llevar a un lugar distinto de donde estabas:
1. Todo lo que se abre ENCIMA de una pantalla (hoja de detalle, calendario, panel de rachas, visor
   de foto, hoja de instalar, cualquier modal) usa `pushOverlay(cerrar)` al abrir y
   `dismissOverlay(despues)` en TODOS sus controles de cierre (X, fondo, Esc, Guardar, Borrar)
   (js/api.js). Atras cierra lo abierto y te deja en la misma pantalla. Nunca cerrar con
   `elemento.remove()` suelto: desordena el historial. Lo que haya que hacer despues de cerrar
   (recargar, ir a otro dia, abrir otra hoja) se pasa como `despues`.
2. Un flujo que se inicia desde el diario (escanear -> confirmar, buscar -> confirmar) ocupa UNA
   sola entrada del historial: dentro del flujo se navega con `location.replace` (enlaces con
   `data-replace`), y al terminar o cancelar se usa `leaveFlow(fallback)` / `data-leave`, que
   retrocede al diario. El diario marca el inicio del flujo (`cadence_from_index`) y al volver
   aplica `applyReturnHints()` (abre el dia guardado y muestra el aviso) tambien en `pageshow`.
3. Cambiar de dia o de mes dentro de una pantalla no agrega historial (`replaceState`).
4. Probar siempre con Playwright (`page.goBack()`): abrir hoja -> Atras = misma pantalla;
   diario -> buscar -> confirmar -> guardar -> Atras = sale del diario, no reentra al flujo.

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
