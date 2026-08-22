import os

from urllib.parse import urlparse

from scrapy import Request
from scrapy.pipelines.files import FilesPipeline


class DataFilesPipeline(FilesPipeline):
    """
    Pipeline encargado de descargar los archivos encontrados
    por el crawler y conservar su nombre original.
    """

    def file_path(
        self,
        request,
        response=None,
        info=None,
        *,
        item=None,
    ):
        filename = request.meta.get(
            "original_filename"
        )

        if not filename:
            filename = os.path.basename(
                urlparse(request.url).path
            )

        if not filename:
            filename = "archivo_descargado"

        # Evitar problemas con nombres de archivos
        filename = filename.replace("\\", "_")
        filename = filename.replace("/", "_")

        return filename

    def get_media_requests(
        self,
        item,
        info,
    ):
        for file_url in item.get(
            "file_urls",
            [],
        ):
            yield Request(
                url=file_url,
                meta={
                    "original_filename": item.get(
                        "original_filename"
                    )
                },
                callback=self._download_file,
            )

    def _download_file(
        self,
        response,
    ):
        """
        No necesitamos procesar el contenido.
        FilesPipeline se encarga de la descarga.
        """
        return response