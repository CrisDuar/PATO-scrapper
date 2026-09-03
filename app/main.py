import json
import os
import sys
import time
import uuid
import threading
import subprocess

from pathlib import Path
from typing import List, Optional

from fastapi import (
    FastAPI,
    HTTPException,
)

from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.config import (
    APP_NAME,
    APP_VERSION,
    BASE_DIR,
    DOWNLOADS_DIR,
    SCRAPY_MAX_DEPTH,
    MAX_PAGES,
    FILE_EXTENSIONS,
)

from app.cleaner.clean_job import clean_job_files
from app.cleaner.loader import load_tables_from_dir

from app.cepal_client import (
    buscar_indicadores,
    descargar_datos_indicador,
    transformar_a_formato_estandar,
    CepalApiError,
)

from app.cepal_dimensions_export import (
    build_dataframe as build_cepal_dimensions_dataframe,
    get_indicator_metadata as get_cepal_indicator_metadata,
    to_preview_records as cepal_dimensions_preview_records,
    CepalDimensionsError,
)




SPIDER_FILE = (
    BASE_DIR
    / "app"
    / "scraper"
    / "ipm_spider.py"
)

CEPAL_EXPORTS_DIR = DOWNLOADS_DIR / "cepal_exports"
CEPAL_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)




app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Sistema de descubrimiento y descarga automática "
        "de archivos relacionados con una temática."
    ),
)




jobs: dict = {}

jobs_lock = threading.Lock()



class JobRequest(BaseModel):

    urls: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "URLs iniciales desde las cuales comenzará "
            "el descubrimiento."
        ),
    )

    @field_validator("urls")
    @classmethod
    def add_scheme(cls, urls: list[str]) -> list[str]:
        """
        Normaliza las URLs recibidas para que siempre
        tengan un esquema (http/https). Sin esto, Scrapy
        no puede construir el Request inicial y además
        urlparse() no logra extraer el hostname, lo que
        deja allowed_domains vacío y bloquea todo el crawl.
        """

        fixed = []

        for url in urls:

            url = url.strip()

            if not url.startswith(
                ("http://", "https://")
            ):
                url = "https://" + url

            fixed.append(url)

        return fixed

    query: List[str] = Field(
    default=["IPM"],
    description="Lista de palabras o frases utilizadas para descubrir contenido relacionado"
)

    max_depth: Optional[int] = Field(
        None,
        ge=0,
        le=30,
    )

    max_pages: Optional[int] = Field(
        None,
        ge=1,
        le=10000,
    )

    allowed_domains: Optional[list[str]] = None

    extensions: Optional[list[str]] = None




def _monitor_job(
    job_id: str,
    process: subprocess.Popen,
    output_handle,
):

    process.wait()

    try:
        output_handle.close()

    except Exception:
        pass

    with jobs_lock:

        job = jobs.get(job_id)

        if not job:
            return

        if process.returncode == 0:
            job["status"] = "completado"

        else:
            job["status"] = "error"

        job["return_code"] = process.returncode

        job["finished_at"] = time.time()




@app.post("/jobs")
def create_job(
    req: JobRequest,
):

    if not req.urls:
        raise HTTPException(
            status_code=400,
            detail="Debes proporcionar al menos una URL.",
        )



    if not SPIDER_FILE.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                f"No existe el spider: "
                f"{SPIDER_FILE}"
            ),
        )


    job_id = str(
        uuid.uuid4()
    )

    job_dir = (
        DOWNLOADS_DIR
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    process_output = (
        job_dir
        / "process_output.log"
    )

    scrapy_log = (
        job_dir
        / "scrapy.log"
    )



    max_depth = (
        req.max_depth
        if req.max_depth is not None
        else SCRAPY_MAX_DEPTH
    )

    max_pages = (
        req.max_pages
        if req.max_pages is not None
        else MAX_PAGES
    )



    cmd = [
        sys.executable,

        "-m",
        "scrapy",

        "runspider",

        str(SPIDER_FILE),

        "-a",
        f"start_urls={','.join(req.urls)}",

        "-a",
        f"query={','.join(req.query)}",

        "-a",
        f"max_depth={max_depth}",

        "-a",
        f"max_pages={max_pages}",

        "-a",
        f"job_id={job_id}",

        "-s",
        f"FILES_STORE={job_dir}",

        "-s",
        f"LOG_FILE={scrapy_log}",
    ]


    if req.allowed_domains:

        cmd += [
            "-a",
            (
                "allowed_domains="
                + ",".join(
                    req.allowed_domains
                )
            ),
        ]



    if req.extensions:

        normalized_extensions = []

        for extension in req.extensions:

            extension = extension.strip().lower()

            if not extension.startswith("."):
                extension = "." + extension

            normalized_extensions.append(
                extension
            )

        cmd += [
            "-a",
            (
                "extensions="
                + ",".join(
                    normalized_extensions
                )
            ),
        ]

    else:

        cmd += [
            "-a",
            (
                "extensions="
                + ",".join(
                    FILE_EXTENSIONS
                )
            ),
        ]


    env = os.environ.copy()

    env["PYTHONPATH"] = (
        str(BASE_DIR)
        + os.pathsep
        + env.get(
            "PYTHONPATH",
            "",
        )
    )



    output_handle = open(
        process_output,
        "w",
        encoding="utf-8",
        errors="ignore",
    )

    process = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        stdout=output_handle,
        stderr=subprocess.STDOUT,
    )


    with jobs_lock:

        jobs[job_id] = {

            "status":
                "en_progreso",

            "urls":
                req.urls,

            "query":
                req.query,

            "max_depth":
                max_depth,

            "max_pages":
                max_pages,

            "created_at":
                time.time(),

            "process":
                process,
        }

    threading.Thread(
        target=_monitor_job,
        args=(
            job_id,
            process,
            output_handle,
        ),
        daemon=True,
    ).start()

    return {
        "job_id": job_id,
        "status": "en_progreso",
        "query": req.query,
        "max_depth": max_depth,
        "max_pages": max_pages,
    }




@app.get("/jobs")
def list_jobs():

    with jobs_lock:

        return [
            {
                "job_id": job_id,
                "status": job["status"],
                "urls": job["urls"],
                "query": job["query"],
            }

            for job_id, job
            in jobs.items()
        ]



@app.get("/jobs/{job_id}")
def get_job_status(
    job_id: str,
):

    with jobs_lock:

        job = jobs.get(
            job_id
        )

    if not job:

        raise HTTPException(
            status_code=404,
            detail="Job no encontrado.",
        )

    job_dir = (
        DOWNLOADS_DIR
        / job_id
    )

    files = []

    if job_dir.exists():

        files = [
            file.name

            for file
            in job_dir.iterdir()

            if (
                file.is_file()
                and file.suffix.lower()
                not in {
                    ".log",
                }
            )
        ]

    return {

        "job_id":
            job_id,

        "status":
            job["status"],

        "urls":
            job["urls"],

        "query":
            job["query"],

        "archivos_encontrados":
            files,
    }




@app.get(
    "/jobs/{job_id}/download/{filename}"
)
def download_file(
    job_id: str,
    filename: str,
):

    job_dir = (
        DOWNLOADS_DIR
        / job_id
    ).resolve()

    file_path = (
        job_dir
        / filename
    ).resolve()

    # Seguridad contra path traversal

    if job_dir not in file_path.parents:

        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado.",
        )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado.",
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado.",
        )

    return FileResponse(
        str(file_path),
        filename=file_path.name,
    )




@app.get(
    "/jobs/{job_id}/log",
    response_class=PlainTextResponse,
)
def get_job_log(
    job_id: str,
):

    job_dir = (
        DOWNLOADS_DIR
        / job_id
    )

    process_log = (
        job_dir
        / "process_output.log"
    )

    scrapy_log = (
        job_dir
        / "scrapy.log"
    )

    if (
        not process_log.exists()
        and not scrapy_log.exists()
    ):

        raise HTTPException(
            status_code=404,
            detail="Log no encontrado.",
        )

    parts = []

    if process_log.exists():

        content = process_log.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        if content.strip():

            parts.append(
                "===== process_output.log =====\n"
                + content
            )

    if scrapy_log.exists():

        content = scrapy_log.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        if content.strip():

            parts.append(
                "===== scrapy.log =====\n"
                + content
            )

    return "\n\n".join(parts)



@app.post("/jobs/{job_id}/clean")
def clean_job(
    job_id: str,
):

    job_dir = (
        DOWNLOADS_DIR
        / job_id
    )

    if not job_dir.exists():

        raise HTTPException(
            status_code=404,
            detail="Job no encontrado.",
        )

    try:
        result = clean_job_files(job_dir)

    except FileNotFoundError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    if not result["archivos_procesados"]:

        raise HTTPException(
            status_code=422,
            detail=(
                "No se encontraron archivos tabulares "
                "(.xlsx, .xls, .csv) para limpiar en este job."
            ),
        )

    return {
        "job_id": job_id,
        **result,
    }


@app.post("/jobs/{job_id}/clean/load")
def load_clean_job(
    job_id: str,
):


    clean_dir = (
        DOWNLOADS_DIR
        / job_id
        / "datos_limpios"
    )

    if not clean_dir.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Aún no se ha generado la limpieza de este job. "
                f"Ejecuta primero POST /jobs/{job_id}/clean."
            ),
        )

    try:
        report = load_tables_from_dir(clean_dir, job_id=job_id)

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    return {
        "job_id": job_id,
        "reporte": report,
    }


@app.get("/jobs/{job_id}/clean/load/log")
def get_load_log(
    job_id: str,
):


    log_path = (
        DOWNLOADS_DIR
        / job_id
        / "datos_limpios"
        / "carga_log.json"
    )

    if not log_path.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Aún no se ha registrado ninguna carga para este job. "
                f"Ejecuta primero POST /jobs/{job_id}/clean/load."
            ),
        )

    return json.loads(log_path.read_text(encoding="utf-8"))


@app.get("/jobs/{job_id}/clean/download")
def download_clean_excel(
    job_id: str,
):
    """
    Descarga el Excel consolidado (datos_limpios.xlsx, una hoja por
    sub-tabla) generado por POST /jobs/{job_id}/clean.
    """

    output_path = (
        DOWNLOADS_DIR
        / job_id
        / "datos_limpios"
        / "datos_limpios.xlsx"
    )

    if not output_path.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Aún no se ha generado 'datos_limpios.xlsx'. "
                f"Ejecuta primero POST /jobs/{job_id}/clean."
            ),
        )

    return FileResponse(
        str(output_path),
        filename=output_path.name,
    )


@app.get("/jobs/{job_id}/clean/download/{table_name}")
def download_clean_table(
    job_id: str,
    table_name: str,
):

    job_dir = (
        DOWNLOADS_DIR
        / job_id
    )

    output_path = (
        job_dir
        / "datos_limpios"
        / f"{table_name}.csv"
    )

    if not output_path.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                f"No existe la tabla '{table_name}' para este job. "
                f"Ejecuta primero POST /jobs/{job_id}/clean y revisa "
                "'archivos_salida' en la respuesta para ver las "
                "tablas disponibles."
            ),
        )

    return FileResponse(
        str(output_path),
        filename=output_path.name,
    )


class CepalExportRequest(BaseModel):

    indicator_id: int = Field(
        ...,
        description=(
            "ID numérico del indicador en CEPALSTAT "
            "(usa GET /cepal/buscar-indicador para encontrarlo)."
        ),
    )

    lang: str = Field(
        "es",
        description="Idioma de los datos: 'es' o 'en'.",
    )

    fuente: str = Field(
        "CEPALSTAT",
        description="Texto a usar en la columna 'fuente' del CSV resultante.",
    )


@app.get("/cepal/buscar-indicador")
def cepal_buscar_indicador(
    nombre: str,
    lang: str = "es",
):
    

    try:
        resultados = buscar_indicadores(nombre, lang=lang)

    except CepalApiError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=f"Error consultando CEPALSTAT: {exc}",
        )

    if not resultados:

        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron indicadores que contengan '{nombre}'.",
        )

    return {
        "query": nombre,
        "resultados": resultados,
    }


@app.post("/cepal/export")
def cepal_export(
    req: CepalExportRequest,
):
    

    try:
        df_crudo = descargar_datos_indicador(
            req.indicator_id,
            lang=req.lang,
        )

        df_csv = transformar_a_formato_estandar(
            df_crudo,
            fuente=req.fuente,
        )

    except CepalApiError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    export_id = str(uuid.uuid4())

    filename = f"cepal_indicador_{req.indicator_id}_{export_id}.csv"

    filepath = CEPAL_EXPORTS_DIR / filename

    df_csv.to_csv(filepath, index=False, encoding="utf-8")

    return {
        "export_id": export_id,
        "filename": filename,
        "filas": len(df_csv),
        "columnas": list(df_csv.columns),
        "muestra": df_csv.head(5).to_dict(orient="records"),
    }


class CepalDimensionsExportRequest(BaseModel):

    indicator_id: int = Field(
        ...,
        description=(
            "ID numérico del indicador en CEPALSTAT "
            "(usa GET /cepal/buscar-indicador para encontrarlo)."
        ),
    )


@app.post("/cepal/export-dimensiones")
def cepal_export_dimensiones(
    req: CepalDimensionsExportRequest,
):

    try:
        df_csv = build_cepal_dimensions_dataframe(req.indicator_id)

    except CepalDimensionsError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    if df_csv.empty:

        raise HTTPException(
            status_code=422,
            detail=(
                f"El indicador {req.indicator_id} no devolvió datos."
            ),
        )

    export_id = str(uuid.uuid4())

    filename = (
        f"cepal_indicador_{req.indicator_id}"
        f"_dimensiones_{export_id}.csv"
    )

    filepath = CEPAL_EXPORTS_DIR / filename

    df_csv.to_csv(filepath, index=False, encoding="utf-8")

    return {
        "export_id": export_id,
        "filename": filename,
        "filas": len(df_csv),
        "columnas": list(df_csv.columns),
        "muestra": cepal_dimensions_preview_records(df_csv),
    }


@app.get("/cepal/export/{filename}/download")
def cepal_export_download(
    filename: str,
):

    filepath = (CEPAL_EXPORTS_DIR / filename).resolve()

    if (
        CEPAL_EXPORTS_DIR.resolve() not in filepath.parents
        or not filepath.exists()
    ):

        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado.",
        )

    return FileResponse(
        str(filepath),
        filename=filename,
        media_type="text/csv",
    )


@app.get("/health")
def health():

    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
    }