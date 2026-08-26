# PATO-scrapper
Web scrapper for PATO

Sistema de descubrimiento y descarga automática de archivos relacionados con una temática (por defecto, el **IPM — Índice de Pobreza Multidimensional**), construido sobre **FastAPI** + **Scrapy**.

Le das una o varias URLs de partida (por ejemplo el sitio del DANE) y el sistema:

1. Rastrea el sitio a partir de esas URLs.
2. Identifica páginas y enlaces relevantes según una temática/query.
3. Descarga los archivos (PDF, Excel, CSV, ZIP, etc.) que encuentre relacionados con esa temática.
4. Expone todo el proceso como *jobs* asíncronos vía API REST.

Además, incluye un **módulo de limpieza de datos** que toma los archivos tabulares (`.xlsx`, `.xls`, `.csv`) descargados por un job, extrae las tablas que contienen, normaliza encabezados y valores, y exporta un libro de trabajo consolidado siguiendo el formato estándar definido en `Formato de Datos.xlsx`.



## Tabla de contenido

- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración (.env)](#configuración-env)
- [Ejecutar el servidor](#ejecutar-el-servidor)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Endpoints de la API](#endpoints-de-la-api)
- [Módulo de limpieza de datos](#módulo-de-limpieza-de-datos)
- [Pruebas](#pruebas)
- [Uso con Postman](#uso-con-postman)
- [Notas y buenas prácticas](#notas-y-buenas-prácticas)

---

## Requisitos

- Python 3.10+
- pip

Dependencias principales:

```
fastapi
uvicorn
scrapy
pydantic
python-dotenv
openpyxl
pandas
psycopg2-binary
```

## Instalación
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Configuración (.env)

Todas las variables son opcionales; si no existen, se usan los valores por defecto definidos en `app/config.py`.

| Variable | Default | Descripción |
|---|---|---|
| `APP_NAME` | `PATO Data Discovery` | Nombre de la app |
| `APP_VERSION` | `3.0.0` | Versión mostrada en `/health` |
| `API_HOST` | `127.0.0.1` | Host donde corre uvicorn |
| `API_PORT` | `8000` | Puerto donde corre uvicorn |
| `SCRAPY_MAX_DEPTH` | `10` | Profundidad máxima de rastreo |
| `SCRAPY_CONCURRENT_REQUESTS` | `8` | Peticiones concurrentes |
| `SCRAPY_DOWNLOAD_DELAY` | `0.5` | Delay entre descargas (segundos) |
| `SCRAPY_ROBOTSTXT_OBEY` | `true` | Respetar `robots.txt` |
| `SCRAPY_USER_AGENT` | `PATO-DataDiscovery/3.0` | User-Agent del crawler |
| `LOG_LEVEL` | `INFO` | Nivel de log de Scrapy |
| `MIN_LINK_SCORE` | `20` | Score mínimo para seguir un enlace |
| `MIN_PAGE_SCORE` | `15` | Score mínimo para marcar una página como relevante |
| `MIN_FILE_SCORE` | `20` | Score mínimo para descargar un archivo |
| `MAX_PAGES` | `1000` | Tope de páginas visitadas por job |
| `DOWNLOADS_DIR` | `downloads` | Carpeta donde se guardan los archivos descargados |
| `FILE_EXTENSIONS` | `.pdf,.xlsx,.xls,.csv,.zip,.rar,.7z,.json,.xml,.txt,.doc,.docx` | Extensiones consideradas "archivo descargable" |
| `DISCOVERY_KEYWORDS` | `datos,estadisticas,indicadores,...` | Palabras que suman puntos a páginas/enlaces de portales estadísticos |
| `DATABASE_URL` | *(vacío)* | Cadena de conexión a PostgreSQL (`postgresql://usuario:password@host:puerto/bd`). Solo requerida para `POST /jobs/{job_id}/clean/load`. Si el usuario/contraseña tienen caracteres especiales (`@`, `:`, etc.), deben ir con percent-encoding (p. ej. `n0mep%40gan%3Av`). |

Ejemplo de `.env`:

```env
API_PORT=8000
MIN_LINK_SCORE=15
MAX_PAGES=500
DOWNLOADS_DIR=downloads
```

## Ejecutar el servidor

```bash
python run.py
```

Esto levanta uvicorn en `API_HOST:API_PORT` (por defecto `http://127.0.0.1:8000`) con `reload=True`.

La documentación interactiva de FastAPI queda disponible en:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Estructura del proyecto

```
app/
├── config.py                     # Configuración centralizada (.env)
├── main.py                       # API FastAPI: crear/consultar/descargar jobs, limpieza de datos
├── scraper/
│   ├── ipm_spider.py             # Spider de Scrapy (lógica de rastreo)
│   ├── crawler/
│   │   ├── url_utils.py          # Normalización de URLs, dominios, nombres de archivo
│   │   ├── link_scorer.py        # Puntaje de relevancia de enlaces
│   │   ├── page_classifier.py    # Puntaje de relevancia de páginas
│   │   └── file_scorer.py        # Puntaje de relevancia de archivos encontrados
│   └── pipelines/
│       └── files_pipeline.py     # Descarga de archivos conservando su nombre original
└── cleaner/
    ├── clean_job.py              # Orquesta la limpieza de todos los archivos de un job
    ├── block_extractor.py        # Extrae bloques de tablas desde CSV/XLS/XLSX (incluye despivote ancho→largo)
    ├── normalizer.py             # Normaliza encabezados y valores de los bloques
    ├── schema.py                 # Definición declarativa de las sub-tablas del esquema objetivo
    ├── table_mapper.py           # Clasifica bloques en sub-tablas y mapea sus columnas
    ├── exporter.py                # Exporta cada sub-tabla como CSV y a un Excel consolidado
    ├── db.py                     # Conexión a PostgreSQL, transacciones y UPSERT idempotente
    ├── loader.py                 # Carga los CSV de un job a PostgreSQL y registra el resultado
    ├── star_schema_mapper.py     # Traduce sub-tablas planas al esquema estrella real (geographic_area/indicator/ipm_statistic)
    ├── ddl.sql                   # DDL de referencia (histórico; el esquema real en BD es geographic_area/indicator/ipm_statistic, ver más abajo)
    └── text_utils.py             # Utilidades de texto compartidas
run.py                            # Punto de entrada (uvicorn)
Formato de Datos.xlsx             # Plantilla/layout de referencia para el esquema de salida
downloads/                        # Carpeta de salida (un subdirectorio por job_id)
tests/
├── conftest.py                   # Fixture requires_db: salta tests si no hay conexión a PostgreSQL
└── test_loader.py                # Pruebas de carga e integración contra la base de datos real
```

Cada job crea una carpeta `downloads/<job_id>/` con:
- Los archivos descargados.
- `process_output.log` (stdout/stderr del proceso Scrapy).
- `scrapy.log` (log interno de Scrapy).
- `datos_limpios/` (una vez ejecutada la limpieza: un CSV por sub-tabla, ver [Módulo de limpieza de datos](#módulo-de-limpieza-de-datos)).
  - `carga_log.json` (una vez ejecutada `POST /jobs/{job_id}/clean/load`: historial de cada intento de carga a PostgreSQL, ver [Endpoints de la API](#endpoints-de-la-api)).

---

## Endpoints de la API

### `POST /jobs`

Crea un nuevo job de descubrimiento y descarga. Se ejecuta en segundo plano (no bloquea la respuesta).

**Body (JSON):**

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `urls` | `string[]` | Sí | URLs de partida. Se les agrega `https://` automáticamente si no tienen esquema. |
| `query` | `string[]` | No (default `["IPM"]`) | Palabras/frases usadas para el descubrimiento. |
| `max_depth` | `int` (0-30) | No | Profundidad máxima de rastreo. |
| `max_pages` | `int` (1-10000) | No | Máximo de páginas a visitar. |
| `allowed_domains` | `string[]` | No | Dominios permitidos. Si no se especifica, se infiere del dominio de las `urls`. |
| `extensions` | `string[]` | No | Extensiones de archivo a buscar (ej. `["pdf", "xlsx"]`). |

**Respuesta:**

```json
{
  "job_id": "3f2a1c7e-...",
  "status": "en_progreso",
  "query": ["IPM"],
  "max_depth": 10,
  "max_pages": 1000
}
```

### `GET /jobs`

Lista todos los jobs creados (en memoria, se pierden al reiniciar el servidor).

**Respuesta:**

```json
[
  {
    "job_id": "3f2a1c7e-...",
    "status": "completado",
    "urls": ["https://www.dane.gov.co"],
    "query": ["IPM"]
  }
]
```

### `GET /jobs/{job_id}`

Consulta el estado de un job y los archivos encontrados hasta el momento.

**Respuesta:**

```json
{
  "job_id": "3f2a1c7e-...",
  "status": "en_progreso",
  "urls": ["https://www.dane.gov.co"],
  "query": ["IPM"],
  "archivos_encontrados": ["boletin_ipm_2023.pdf", "anexo_ipm.xlsx"]
}
```

`status` puede ser: `en_progreso`, `completado`, `error`.

### `GET /jobs/{job_id}/download/{filename}`

Descarga un archivo específico encontrado por el job. `filename` debe ser uno de los que aparecen en `archivos_encontrados`.

Devuelve el archivo binario (`FileResponse`).

### `GET /jobs/{job_id}/log`

Devuelve el log combinado (`process_output.log` + `scrapy.log`) como texto plano. Útil para depurar por qué un job no encuentra nada.

### `GET /health`

Chequeo de salud del servicio.

```json
{ "status": "ok", "app": "PATO Data Discovery", "version": "3.0.0" }
```

### `POST /jobs/{job_id}/clean`

Limpia y clasifica los archivos tabulares (`.xlsx`, `.xls`, `.csv`) descargados por el job en las sub-tablas normalizadas del esquema objetivo (ver [Módulo de limpieza de datos](#módulo-de-limpieza-de-datos)). Genera un CSV por sub-tabla en `downloads/<job_id>/datos_limpios/`.

**Respuesta:**

```json
{
  "job_id": "3f2a1c7e-...",
  "archivos_procesados": ["anex-PMultidimensional-2025.xlsx"],
  "bloques_detectados": 177,
  "filas_por_tabla": {
    "ipm_por_dominio": 46,
    "privaciones_por_hogar": 660,
    "proporcion_privaciones": 40,
    "contribuciones_incidencia": 90,
    "incidencia_por_sexo_persona": 36,
    "incidencia_por_sexo_jefe_hogar": 36,
    "dashboard_02": 0,
    "contribucion_relativa_privaciones": 0,
    "poblacion_pobreza_multidimensional": 0,
    "sin_clasificar": 85
  },
  "archivos_salida": {
    "ipm_por_dominio": "downloads/3f2a1c7e-.../datos_limpios/ipm_por_dominio.csv",
    "excel": "downloads/3f2a1c7e-.../datos_limpios/datos_limpios.xlsx",
    "...": "..."
  }
}
```

Además de los CSV, genera un único **Excel consolidado** (`datos_limpios.xlsx`) con una hoja por sub-tabla no vacía (mismos datos que los CSV, encabezados en negrita) para revisión manual rápida.

Errores:
- `404` si el job no existe.
- `422` si el job no tiene archivos `.xlsx`/`.xls`/`.csv` para limpiar.

### `GET /jobs/{job_id}/clean/download`

Descarga el Excel consolidado (`datos_limpios.xlsx`, una hoja por sub-tabla) generado por `POST /jobs/{job_id}/clean`. Devuelve `404` si aún no se ha ejecutado la limpieza.

### `GET /jobs/{job_id}/clean/download/{table_name}`

Descarga el CSV de una sub-tabla específica (p. ej. `ipm_por_dominio`, `privaciones_por_hogar`) generada por `POST /jobs/{job_id}/clean`. Los nombres válidos aparecen en `archivos_salida` de esa respuesta. Devuelve `404` si la tabla no existe para ese job (no se generó limpieza, o esa sub-tabla quedó vacía).

También acepta `sin_clasificar`: no es una sub-tabla del esquema, sino un CSV aparte (columnas `title, headers, source_file, source_sheet, row_count`) con los bloques que no calzaron en ninguna sub-tabla, útil para revisión manual.

### `POST /jobs/{job_id}/clean/load`

Carga a PostgreSQL las sub-tablas ya limpiadas de este job que tienen mapeo acordado al esquema estrella real (`ipm_por_dominio`, `proporcion_privaciones`, `privaciones_por_hogar` — ver [Carga a PostgreSQL](#carga-a-postgresql)), con `UPSERT` idempotente. Toda la carga del job corre en **una sola transacción**: si alguna tabla falla, se revierte el job completo (no quedan filas parciales). Requiere `DATABASE_URL` configurada en `.env`; devuelve `503` si no lo está. El resultado queda registrado en `downloads/<job_id>/datos_limpios/carga_log.json`.

**Respuesta:**

```json
{
  "job_id": "3f2a1c7e-...",
  "reporte": {
    "ipm_por_dominio": { "insertadas": 46, "rechazadas": 0 },
    "privaciones_por_hogar": { "insertadas": 660, "rechazadas": 0 },
    "proporcion_privaciones": { "insertadas": 40, "rechazadas": 0 },
    "contribuciones_incidencia": {
      "insertadas": 0, "rechazadas": 0, "omitidas": 90,
      "motivo": "Sin mapeo acordado al esquema de PostgreSQL; disponible solo en el CSV/Excel exportado."
    },
    "...": "..."
  }
}
```

Si una tabla falla (p. ej. error de conexión o de datos), su entrada trae `"error": "..."` y `rechazadas` igual al total de filas de esa tabla; como la carga es transaccional, ninguna otra tabla del mismo job queda insertada tampoco.

### `GET /jobs/{job_id}/clean/load/log`

Devuelve el historial completo de cargas a PostgreSQL de este job (`carga_log.json`): uno o más intentos, cada uno con fecha, totales insertados/rechazados, si fue exitoso, y el detalle por tabla. Devuelve `404` si el job aún no tiene ninguna carga registrada.

**Respuesta:**

```json
[
  {
    "job_id": "3f2a1c7e-...",
    "fecha_carga": "2026-08-26T00:09:03.397696+00:00",
    "total_insertadas": 525,
    "total_rechazadas": 0,
    "exito": true,
    "detalle": { "...": "..." }
  }
]
```

---

## Módulo de limpieza de datos

El módulo `app/cleaner/` toma los archivos descargados por un job y los transforma en **sub-tablas normalizadas**, listas para cargar a PostgreSQL y alimentar el servicio de IA Predictiva y el Dashboard Geoespacial del proyecto PATO.

Flujo (orquestado por `clean_job_files` en [clean_job.py](app/cleaner/clean_job.py)):

1. **Extracción** (`block_extractor.py`): recorre cada archivo `.csv`/`.xls`/`.xlsx` del job y detecta bloques de tabla dentro de cada hoja/archivo. Reconoce varios patrones comunes en los anexos del DANE:
   - **Ancho por año** (`Dominio | Año → 2010 2011 2012...`): una columna por año, despivotado a formato largo.
   - **Matricial** (`Dimensión | Principales Dominios → Nacional Cabecera Rural...`): una columna por dominio/región/país, despivotado a formato largo.
   - **Celdas combinadas (merged cells)**: propaga verticalmente el valor de una celda fusionada sobre varias filas de datos (p. ej. una etiqueta 'Sexo' fusionada sobre las filas Hombre/Mujer).
   - **Columna "huérfana"**: cuando el DANE deja en blanco (sin merge real) la celda de categoría en filas subsiguientes de un mismo grupo (p. ej. 'Nacional' solo en la primera fila de una lista de variables), se propaga hacia abajo con un forward-fill acotado a filas con la misma forma.
2. **Normalización** (`normalizer.py`): repara encoding, recorta espacios, homogeniza tipos de dato y elimina filas duplicadas/vacías.
3. **Clasificación y mapeo** (`table_mapper.py`): decide a qué sub-tabla del esquema pertenece cada bloque (según sus columnas y, cuando hace falta desambiguar, el título del bloque), renombra columnas a los nombres destino, castea tipos (`int`/`float`/`boolean`/`text`) y deduplica por la clave natural de cada tabla.
4. **Exportación** (`exporter.py`): escribe cada sub-tabla como un CSV en `downloads/<job_id>/datos_limpios/`, con metadatos de trazabilidad (`fuente`, `fecha_extraccion`, `fecha_carga`).

Bloques que no calzan con ninguna sub-tabla quedan en `sin_clasificar.csv` (título, encabezados y archivo de origen) para revisión manual.

**Sub-tablas del esquema** (definidas en [schema.py](app/cleaner/schema.py)):

| Tabla | Dashboard | Columnas | Estado |
|---|---|---|---|
| `ipm_por_dominio` | 01 | `anio, dominio, ipm` | ✅ Verificado con datos reales del DANE |
| `privaciones_por_hogar` | 01 | `anio, dominio, variable, ipm` | ✅ Verificado con datos reales del DANE |
| `proporcion_privaciones` | 01 | `anio, dominio, porcentaje` | ✅ Verificado con datos reales del DANE |
| `contribuciones_incidencia` | 01 | `anio, dominio, dimension, porcentaje` | ✅ Verificado con datos reales del DANE |
| `incidencia_por_sexo_persona` | 01 | `anio, dominio, sexo, porcentaje` | ✅ Verificado con datos reales del DANE (requirió soporte de celdas combinadas en `block_extractor.py`) |
| `incidencia_por_sexo_jefe_hogar` | 01 | `anio, dominio, sexo, porcentaje` | ✅ Verificado con datos reales del DANE |
| `dashboard_02` | 02 | `anio, region, departamento, personas_hogar, priv_*, ipm, pobre` | ⏳ Esquema y mapeo de columnas listos (`Pobreza Multidimensional Hogares Departamental`); se llenará automáticamente cuando el scraper encuentre y descargue esa fuente de microdatos por hogar |
| `contribucion_relativa_privaciones` | 03 | `anio, privacion, pais, valor_porcentaje` | ⏳ Esquema listo — requiere el anexo Latinoamérica del DANE, aún no encontrado por el scraper |
| `poblacion_pobreza_multidimensional` | 03 | `anio, area_geografica, pais, tipo_medida, valor_porcentaje` | ⏳ Esquema listo — mismo motivo que la anterior |

### Carga a PostgreSQL

La base de datos compartida del proyecto (`clean_data_db`) usa un **esquema estrella** ya provisionado por el equipo, distinto de las 9 sub-tablas planas de arriba:

| Tabla | Descripción |
|---|---|
| `geographic_area` | Catálogo de áreas geográficas (`id`, `parent_id`, `level`, `name`, `country_iso_code`, `official_code`). Sin `UNIQUE` de negocio — la deduplicación por `(name, level)` la hace la aplicación. |
| `indicator` | Catálogo de indicadores (`id`, `code` único, `name`, `category`). |
| `ipm_statistic` | Tabla de hechos (`geographic_area_id`, `indicator_id`, `period`, `breakdown_type`, `breakdown_value`, `value`, `source`, `extracted_at`, `loaded_at`), con `UNIQUE(geographic_area_id, indicator_id, period, breakdown_type, breakdown_value)` como clave natural real. |

De las 9 sub-tablas planas, solo **3 tienen convención de `indicator.code` acordada** (fijada por las vistas SQL ya existentes en la base — `vw_ipm_by_domain`, `vw_average_deprivations`, `vw_deprivations_by_variable`) y por eso son las únicas que `POST /jobs/{job_id}/clean/load` carga a `ipm_statistic`:

| Sub-tabla plana | `indicator.code` | `indicator.category` | `breakdown_type` |
|---|---|---|---|
| `ipm_por_dominio` | `MPI` (fijo) | `mpi` | `none` |
| `proporcion_privaciones` | `INTENSITY_A` (fijo) | `intensity` | `none` |
| `privaciones_por_hogar` | uno por `variable` (slug en mayúsculas, truncado a 50 caracteres) | `privation_variable` | `none` |

El mapeo lo hace `app/cleaner/star_schema_mapper.py`; `app/cleaner/loader.py` resuelve/crea las filas de `geographic_area` e `indicator` que falten y hace `UPSERT` idempotente (`ON CONFLICT ... DO UPDATE`) sobre la clave natural real de `ipm_statistic`, por lo que reejecutar la carga no duplica filas ni indicadores.

Las otras 6 sub-tablas (`contribuciones_incidencia`, `incidencia_por_sexo_persona`, `incidencia_por_sexo_jefe_hogar`, `dashboard_02`, `contribucion_relativa_privaciones`, `poblacion_pobreza_multidimensional`) **no se cargan a PostgreSQL todavía** — el reporte las marca como `omitidas` con el motivo — porque no tienen convención de `indicator.code`/`breakdown_type` acordada con el equipo (en particular `dashboard_02`, que trae microdatos de hogar con 15 privaciones booleanas por fila y no encaja directamente en el modelo `indicator + value` de una métrica por fila). Siguen disponibles como CSV/Excel para descarga manual.

**Transacciones y manejo de errores**: toda la carga de un job corre dentro de una única transacción (`app/cleaner/db.py::transaction`) — si cualquier tabla falla (error de datos o de conexión), se revierte el job completo, evitando estados parciales en la base compartida. Los errores de PostgreSQL (`psycopg2.Error`) se capturan y se reportan por tabla sin tumbar el proceso.

**Registro del resultado**: cada ejecución de `POST /jobs/{job_id}/clean/load` agrega una entrada a `downloads/<job_id>/datos_limpios/carga_log.json` (fecha, totales insertados/rechazados, éxito, detalle por tabla), acumulando el historial de todos los intentos de carga de ese job. Se consulta con `GET /jobs/{job_id}/clean/load/log`.

El DDL histórico de las 9 tablas planas (no usado por la carga real, que apunta al esquema estrella) está en [ddl.sql](app/cleaner/ddl.sql), como referencia de los tipos de dato de cada columna.

**Uso típico:**

```bash
# 1. Crea el job de scraping y espera a que termine (status: completado)
# 2. Limpia y clasifica los archivos descargados
curl -X POST http://127.0.0.1:8000/jobs/{job_id}/clean

# 3. Descarga el Excel consolidado (todas las sub-tablas en una hoja cada una)
curl -o datos_limpios.xlsx http://127.0.0.1:8000/jobs/{job_id}/clean/download

# 3b. O descarga solo el CSV de una sub-tabla específica
curl -o ipm_por_dominio.csv http://127.0.0.1:8000/jobs/{job_id}/clean/download/ipm_por_dominio

# 4. (Opcional, requiere DATABASE_URL en .env) Carga las 3 sub-tablas soportadas a PostgreSQL
curl -X POST http://127.0.0.1:8000/jobs/{job_id}/clean/load

# 5. Revisa el historial de cargas de este job
curl http://127.0.0.1:8000/jobs/{job_id}/clean/load/log
```

---

## Pruebas

Las pruebas de carga e integración (`tests/test_loader.py`) corren contra la base de datos real definida en `DATABASE_URL` (no hay mocks): validan inserción, idempotencia del `UPSERT`, actualización de valores, rechazo de filas inválidas, el rollback transaccional ante un error a mitad de carga, y el registro en `carga_log.json`. Se saltan automáticamente si `DATABASE_URL` no está configurada o la base no es accesible (`tests/conftest.py::requires_db`).

```bash
pip install -r requirements.txt   # incluye pytest
python -m pytest tests/ -v
```

Cada test aísla sus datos con un nombre de área geográfica único (UUID) para no chocar entre corridas ni con datos reales — el usuario de servicio (`scraper_service`) solo tiene permisos `INSERT`/`SELECT`/`UPDATE` en la base compartida (sin `DELETE`, por diseño), así que las filas de prueba no se limpian al terminar, pero quedan marcadas con `geographic_area.name` empezando en `__test__`.

---

## Uso con Postman

### 1. Crear el job

- **Método:** `POST`
- **URL:** `http://127.0.0.1:8000/jobs`
- **Body → raw → JSON:**

```json
{
  "urls": ["www.dane.gov.co"],
  "query": ["IPM", "pobreza multidimensional"],
  "max_depth": 6,
  "max_pages": 300
}
```

- **Headers:** Postman agrega automáticamente `Content-Type: application/json` cuando eliges `raw` + `JSON` en el Body. No necesitas agregarlo a mano.

- **Respuesta esperada (201/200):**

```json
{
  "job_id": "3f2a1c7e-0b4a-4d3e-9c9a-1234567890ab",
  "status": "en_progreso",
  "query": ["IPM", "pobreza multidimensional"],
  "max_depth": 6,
  "max_pages": 300
}
```

### 2. Consultar el estado del job

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}`

Repite esta petición cada pocos segundos (o usa el Runner de Postman con un delay) hasta que `status` sea `completado` o `error`.

### 3. Listar todos los jobs

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs`

### 4. Ver el log del job (útil si `status` = `error` o si `archivos_encontrados` está vacío)

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/log`

La respuesta es texto plano; en Postman se ve directamente en la pestaña **Body → Pretty (Text)**.

### 5. Descargar un archivo encontrado

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/download/boletin_ipm_2023.pdf`

En Postman, dale clic a **Send and Download** (flechita junto al botón "Send") para guardar el archivo directamente en tu disco, en vez de solo verlo en la pestaña de respuesta.

### 6. Health check

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/health`

### 7. Limpiar y clasificar los datos del job

- **Método:** `POST`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/clean`

No requiere body. Devuelve un resumen de archivos procesados, bloques detectados y filas por sub-tabla (`filas_por_tabla`).

### 8. Descargar el Excel consolidado

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/clean/download`

Usa **Send and Download** para guardar `datos_limpios.xlsx` (una hoja por sub-tabla) en disco.

### 8b. Descargar una sub-tabla limpia como CSV

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/clean/download/ipm_por_dominio`

Cambia `ipm_por_dominio` por cualquier nombre de tabla que haya aparecido en `archivos_salida` del paso anterior. Usa **Send and Download** para guardar el CSV en disco.

### 9. Cargar las sub-tablas a PostgreSQL (opcional)

- **Método:** `POST`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/clean/load`

Requiere `DATABASE_URL` configurada en `.env` (ver tabla de variables); si no lo está, responde `503`. Solo carga `ipm_por_dominio`, `proporcion_privaciones` y `privaciones_por_hogar` (ver [Carga a PostgreSQL](#carga-a-postgresql)); el resto aparece como `omitidas` en el reporte.

### 10. Ver el historial de cargas a PostgreSQL

- **Método:** `GET`
- **URL:** `http://127.0.0.1:8000/jobs/{{job_id}}/clean/load/log`

Devuelve todos los intentos de carga de este job (éxito/error, totales, detalle por tabla). Responde `404` si aún no se ha ejecutado ninguna carga.



## Notas y buenas prácticas

- **Las URLs de `urls` no necesitan `http://` o `https://`**: si las omites, el sistema les antepone `https://` automáticamente.
- **`allowed_domains`** es opcional. Si no lo envías, se infiere automáticamente del dominio de las `urls` que diste — así el crawler no se sale del sitio que le indicaste.
- **Los jobs viven en memoria**: si reinicias el servidor (`python run.py`), se pierde el registro de jobs anteriores (aunque los archivos ya descargados siguen en `downloads/<job_id>/`).
- **Si un job termina con `archivos_encontrados: []`**, revisa primero `/jobs/{job_id}/log`: la causa más común es que el sitio no usa las palabras del `query` en el texto/URL de sus enlaces de navegación, o que el score mínimo (`MIN_LINK_SCORE` / `MIN_FILE_SCORE`) está muy alto para ese sitio en particular. Puedes ajustar esos valores en el `.env`.
- **Descargas masivas**: usa `max_pages` con cabeza en sitios grandes — un valor muy alto puede hacer que el job tarde mucho o sature el sitio objetivo (respeta `SCRAPY_DOWNLOAD_DELAY`).
- **`DATABASE_URL` vacía**: la limpieza (`/clean`) funciona sin PostgreSQL configurado — solo genera los CSV. La carga (`/clean/load`) sí la requiere.
- **La carga a PostgreSQL es transaccional por job**: si una sub-tabla falla al cargar, se revierte todo el job (ninguna fila queda insertada a medias). Revisa `carga_log.json` (o `GET /jobs/{job_id}/clean/load/log`) para ver el detalle del error.
- **Solo 3 de las 9 sub-tablas se cargan a PostgreSQL hoy** (`ipm_por_dominio`, `proporcion_privaciones`, `privaciones_por_hogar`), porque son las únicas con convención de `indicator.code` acordada con el equipo. El resto sigue disponible en CSV/Excel.
- **Significado de las columnas del esquema limpio**: `anio` es el año del dato; `dominio` es el ámbito geográfico del dato — para el DANE son exactamente 3 valores (`Nacional`, `Cabecera(s)`, `Centros poblados y rural disperso`), y en las tablas que además desagregan por región (`contribuciones_incidencia`, `incidencia_por_sexo_*`) también puede tomar el nombre de una región (Caribe, Oriental, Central, etc.) o país (en `dashboard_03`); `variable`/`dimension` es qué se está midiendo (Analfabetismo, Rezago escolar, Educación, Salud...); `ipm`/`porcentaje`/`valor_porcentaje` es el valor del indicador en puntos porcentuales.