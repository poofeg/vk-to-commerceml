import csv
import io
from collections.abc import Iterable


class CsvWriter:
    def __init__(self) -> None:
        self.__csv_file = io.StringIO(newline='')
        self.__writer = csv.DictWriter(
            self.__csv_file,
            fieldnames=[
                'External ID', 'Mark', 'Category', 'Parent UID', 'SEO descr', 'SEO keywords'
            ],
        )
        self.__writer.writeheader()

    def write_row(
        self,
        external_id: str,
        categories: Iterable[str],
        mark: str | None = None,
        seo_descr: str | None = None,
        seo_keywords: str | None = None,
    ) -> None:
        self.__writer.writerow({
            'External ID': external_id,
            'Mark': mark,
            'Category': ';'.join(categories),
            'SEO descr': seo_descr,
            'SEO keywords': seo_keywords,
        })

    def finish(self) -> str:
        value = self.__csv_file.getvalue()
        self.__csv_file.close()
        return value
