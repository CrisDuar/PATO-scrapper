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




SPIDER_FILE = (
    BASE_DIR
    / "app"
    / "scraper"
    / "ipm_spider.py"
)




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
    """
    Carga a PostgreSQL las sub-tablas ya limpiadas de este job
    (ejecutar POST /jobs/{job_id}/clean primero). Requiere que
    DATABASE_URL esté configurada en el .env.
    """

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
        report = load_tables_from_dir(clean_dir)

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    return {
        "job_id": job_id,
        "reporte": report,
    }


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


@app.get("/health")
def health():

    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
    }