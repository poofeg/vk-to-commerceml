import csv
import io
from collections.abc import Iterable


class CsvWriter:
    def __init__(self):
        self.__csv_file = io.StringIO(newline='')
        self.__writer = csv.DictWriter(self.__csv_file, fieldnames=['External ID', 'Mark', 'Category', 'Parent UID'])
        self.__writer.writeheader()

    def write_row(self, external_id: str, categories: Iterable[str], mark: str | None = None) -> None:
        self.__writer.writerow({'External ID': external_id, 'Mark': mark, 'Category': ';'.join(categories)})

    def finish(self) -> str:
        value = self.__csv_file.getvalue()
        self.__csv_file.close()
        return value
