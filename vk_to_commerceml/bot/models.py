from enum import StrEnum
from typing import Final


class Site(StrEnum):
    TILDA = 'tilda'
    CUSTOM = 'custom'


SITE_DISPLAY_NAMES: Final[dict[Site, str]] = {
    Site.TILDA: 'Tilda',
    Site.CUSTOM: 'Другой',
}

SITE_CML_URLS: Final[dict[Site, str]] = {
    Site.TILDA: 'https://store.tilda.ru/connectors/commerceml/',
}

SITE_CATALOG_URLS: Final[dict[Site, str]] = {
    Site.TILDA: 'https://store.tilda.ru/store/?projectid={login}',
    Site.CUSTOM: '{login}',
}
