# PATO-scrapper
Web scrapper for PATO

Sistema de descubrimiento y descarga automática de archivos relacionados con una temática (por defecto, el **IPM — Índice de Pobreza Multidimensional**), construido sobre **FastAPI** + **Scrapy**.

Le das una o varias URLs de partida (por ejemplo el sitio del DANE) y el sistema:

1. Rastrea el sitio a partir de esas URLs.
2. Identifica páginas y enlaces relevantes según una temática/query.
3. Descarga los archivos (PDF, Excel, CSV, ZIP, etc.) que encuentre relacionados con esa temática.
4. Expone todo el proceso como *jobs* asíncronos vía API REST.



## Tabla de contenido

- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración (.env)](#configuración-env)
- [Ejecutar el servidor](#ejecutar-el-servidor)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Endpoints de la API](#endpoints-de-la-api)
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
├── main.py                       # API FastAPI: crear/consultar/descargar jobs
└── scraper/
    ├── ipm_spider.py             # Spider de Scrapy (lógica de rastreo)
    ├── crawler/
    │   ├── url_utils.py          # Normalización de URLs, dominios, nombres de archivo
    │   ├── link_scorer.py        # Puntaje de relevancia de enlaces
    │   ├── page_classifier.py    # Puntaje de relevancia de páginas
    │   └── file_scorer.py        # Puntaje de relevancia de archivos encontrados
    └── pipelines/
        └── files_pipeline.py     # Descarga de archivos conservando su nombre original
run.py                            # Punto de entrada (uvicorn)
downloads/                        # Carpeta de salida (un subdirectorio por job_id)
```

Cada job crea una carpeta `downloads/<job_id>/` con:
- Los archivos descargados.
- `process_output.log` (stdout/stderr del proceso Scrapy).
- `scrapy.log` (log interno de Scrapy).

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



## Notas y buenas prácticas

- **Las URLs de `urls` no necesitan `http://` o `https://`**: si las omites, el sistema les antepone `https://` automáticamente.
- **`allowed_domains`** es opcional. Si no lo envías, se infiere automáticamente del dominio de las `urls` que diste — así el crawler no se sale del sitio que le indicaste.
- **Los jobs viven en memoria**: si reinicias el servidor (`python run.py`), se pierde el registro de jobs anteriores (aunque los archivos ya descargados siguen en `downloads/<job_id>/`).
- **Si un job termina con `archivos_encontrados: []`**, revisa primero `/jobs/{job_id}/log`: la causa más común es que el sitio no usa las palabras del `query` en el texto/URL de sus enlaces de navegación, o que el score mínimo (`MIN_LINK_SCORE` / `MIN_FILE_SCORE`) está muy alto para ese sitio en particular. Puedes ajustar esos valores en el `.env`.
- **Descargas masivas**: usa `max_pages` con cabeza en sitios grandes — un valor muy alto puede hacer que el job tarde mucho o sature el sitio objetivo (respeta `SCRAPY_DOWNLOAD_DELAY`).