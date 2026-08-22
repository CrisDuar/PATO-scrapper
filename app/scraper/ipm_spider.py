import scrapy

from urllib.parse import (
    urlparse,
)

from app.config import (
    FILE_EXTENSIONS,
    SCRAPY_CONCURRENT_REQUESTS,
    SCRAPY_DOWNLOAD_DELAY,
    SCRAPY_ROBOTSTXT_OBEY,
    SCRAPY_USER_AGENT,
    LOG_LEVEL,
    MIN_LINK_SCORE,
    MIN_PAGE_SCORE,
    MIN_FILE_SCORE,
    MAX_PAGES,
)

from app.scraper.crawler.url_utils import (
    normalize_url,
    get_filename,
    get_hostname,
    is_same_domain,
)

from app.scraper.crawler.link_scorer import (
    calculate_link_score,
)

from app.scraper.crawler.page_classifier import (
    calculate_page_score,
)

from app.scraper.crawler.file_scorer import (
    calculate_file_score,
)

from app.scraper.pipelines.files_pipeline import (
    DataFilesPipeline,
)




class DataFileItem(scrapy.Item):

    file_urls = scrapy.Field()

    files = scrapy.Field()

    source_page = scrapy.Field()

    original_filename = scrapy.Field()

    score = scrapy.Field()

    query = scrapy.Field()




class IPMSpider(scrapy.Spider):

    name = "ipm_discovery"

    custom_settings = {

        "ITEM_PIPELINES": {
            "app.scraper.ipm_spider.DataFilesPipeline": 1,
        },

        "ROBOTSTXT_OBEY":
            SCRAPY_ROBOTSTXT_OBEY,

        "CONCURRENT_REQUESTS":
            SCRAPY_CONCURRENT_REQUESTS,

        "DOWNLOAD_DELAY":
            SCRAPY_DOWNLOAD_DELAY,

        "USER_AGENT":
            SCRAPY_USER_AGENT,

        "LOG_LEVEL":
            LOG_LEVEL,

        "HTTPERROR_ALLOW_ALL":
            True,

        "RETRY_TIMES":
            3,

        "DOWNLOAD_TIMEOUT":
            30,

        "DEPTH_LIMIT":
            10,

        "DEPTH_PRIORITY":
            1,

        "SCHEDULER_DISK_QUEUE":
            "scrapy.squeues.PickleFifoDiskQueue",

        "SCHEDULER_MEMORY_QUEUE":
            "scrapy.squeues.FifoMemoryQueue",
    }



    def __init__(
        self,
        start_urls="",
        query="IPM",
        max_depth=None,
        max_pages=None,
        allowed_domains="",
        extensions="",
        job_id="",
        *args,
        **kwargs,
    ):

        super().__init__(
            *args,
            **kwargs,
        )



        self.start_urls = [
            url.strip()
            for url
            in start_urls.split(",")
            if url.strip()
        ]

        if not self.start_urls:

            raise ValueError(
                "Debes proporcionar al menos "
                "una URL inicial."
            )



        self.query = (
            query.strip()
            or "IPM"
        )

        self.query_lower = (
            self.query.lower()
        )

        self.job_id = job_id



        self.max_depth = int(
            max_depth
            if max_depth
            else 10
        )

        self.custom_settings = dict(
            self.custom_settings
        )

        self.custom_settings[
            "DEPTH_LIMIT"
        ] = self.max_depth



        self.max_pages = int(
            max_pages
            if max_pages
            else MAX_PAGES
        )

        self.pages_seen = 0



        if allowed_domains:

            self.allowed_domains = [
                domain.strip().lower()
                for domain
                in allowed_domains.split(",")
                if domain.strip()
            ]

        else:

            self.allowed_domains = list({
                get_hostname(url)

                for url
                in self.start_urls

                if get_hostname(url)
            })



        if extensions:

            parsed_extensions = []

            for extension in extensions.split(","):

                extension = (
                    extension
                    .strip()
                    .lower()
                )

                if not extension:
                    continue

                if not extension.startswith("."):
                    extension = "." + extension

                parsed_extensions.append(
                    extension
                )

            self.file_extensions = tuple(
                parsed_extensions
            )

        else:

            self.file_extensions = (
                FILE_EXTENSIONS
            )



        self.pages_relevant = 0

        self.files_found = 0



        self.free_discovery_depth = 2



    def start_requests(self):

        for url in self.start_urls:

            yield scrapy.Request(
                url,
                callback=self.parse,
                errback=self.handle_error,
                meta={
                    "discovery_depth": 0,
                },
                dont_filter=True,
            )



    def parse(
        self,
        response,
    ):



        self.pages_seen += 1

        if (
            self.pages_seen
            > self.max_pages
        ):

            self.logger.info(
                "MAX_PAGES alcanzado: %s",
                self.max_pages,
            )

            return


        content_type = (
            response.headers
            .get(
                "Content-Type",
                b"",
            )
            .decode(
                "utf-8",
                "ignore",
            )
            .lower()
        )

        if (
            "html"
            not in content_type
        ):

            return



        page_text = " ".join(
            response.css(
                "body *::text"
            ).getall()
        )

        page_score = (
            calculate_page_score(
                response.url,
                page_text,
                self.query,
            )
        )

        if (
            page_score
            >= MIN_PAGE_SCORE
        ):

            self.pages_relevant += 1

            self.logger.info(
                "PÁGINA RELEVANTE [%s]",
                page_score,
            )

            self.logger.info(
                "%s",
                response.url,
            )



        discovery_depth = response.meta.get(
            "discovery_depth",
            0,
        )

        for link in response.css("a"):

            href = link.attrib.get(
                "href"
            )

            if not href:
                continue

            url = normalize_url(
                response.url,
                href,
            )

            if not url:
                continue



            if not is_same_domain(
                url,
                self.allowed_domains,
            ):

                continue


            link_text = " ".join(
                link.css(
                    "::text"
                ).getall()
            ).strip()


            if self.is_file(
                url
            ):

                yield from self.process_file(
                    url,
                    link_text,
                    response.url,
                )

                continue



            link_score = (
                calculate_link_score(
                    url,
                    link_text,
                    self.query,
                )
            )



            should_follow = (
                discovery_depth
                < self.free_discovery_depth
                or link_score
                >= MIN_LINK_SCORE
            )

            if should_follow:

                self.logger.debug(
                    "Siguiendo enlace [%s] (prof. %s): %s",
                    link_score,
                    discovery_depth,
                    url,
                )

                yield response.follow(
                    url,
                    callback=self.parse,
                    errback=self.handle_error,
                    meta={
                        "discovery_depth": discovery_depth + 1,
                    },
                )


    def process_file(
        self,
        url: str,
        link_text: str,
        source_page: str,
    ):

        score = calculate_file_score(
    url=url,
    link_text=link_text,
    query=self.query,
    source_page=source_page,
)

        filename = get_filename(
            url
        )



        if (
            score
            < MIN_FILE_SCORE
        ):

            self.logger.debug(
                "Archivo descartado [%s]: %s",
                score,
                filename,
            )

            return


        self.files_found += 1

        self.logger.info(
            "======================================"
        )

        self.logger.info(
            "ARCHIVO RELACIONADO ENCONTRADO"
        )

        self.logger.info(
            "Score: %s",
            score,
        )

        self.logger.info(
            "Archivo: %s",
            filename,
        )

        self.logger.info(
            "URL: %s",
            url,
        )

        self.logger.info(
            "Página: %s",
            source_page,
        )

        self.logger.info(
            "======================================"
        )

        yield DataFileItem(
            file_urls=[url],

            source_page=source_page,

            original_filename=filename,

            score=score,

            query=self.query,
        )



    def is_file(
        self,
        url: str,
    ) -> bool:

        path = (
            urlparse(url)
            .path
            .lower()
        )

        return any(
            path.endswith(
                extension
            )
            for extension
            in self.file_extensions
        )


    def handle_error(
        self,
        failure,
    ):

        request = failure.request

        self.logger.warning(
            "No se pudo acceder a: %s",
            request.url,
        )

        self.logger.warning(
            "Error: %s",
            failure.value,
        )



    def closed(
        self,
        reason,
    ):

        self.logger.info(
            "======================================"
        )

        self.logger.info(
            "CRAWLER FINALIZADO"
        )

        self.logger.info(
            "Motivo: %s",
            reason,
        )

        self.logger.info(
            "Páginas visitadas: %s",
            self.pages_seen,
        )

        self.logger.info(
            "Páginas relevantes: %s",
            self.pages_relevant,
        )

        self.logger.info(
            "Archivos encontrados: %s",
            self.files_found,
        )

        self.logger.info(
            "======================================"
        )