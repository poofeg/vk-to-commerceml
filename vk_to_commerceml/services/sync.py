import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum

from pydantic import SecretStr

from vk_to_commerceml.infrastructure.cml.client import CmlClient
from vk_to_commerceml.infrastructure.cml.models import (
    Catalog,
    CatalogClassifier,
    DetailValue,
    Group,
    ImportDocument,
    Offer,
    OffersDocument,
    PackageOfOffers,
    Price,
    PriceType,
    Product,
    Property,
    PropertyValue,
)
from vk_to_commerceml.infrastructure.vk import models as vk_models
from vk_to_commerceml.infrastructure.vk.client import VkClient
from vk_to_commerceml.services.csv_writer import CsvWriter

RE_PROPERTIES_AREA = re.compile(r'^(.*?)\s*--\s*(.*)$', re.DOTALL)
RE_PROPERTIES = re.compile(r'^\s*(.*?)\s*:\s*(.*?)\s*$', re.MULTILINE)
RE_FULL_NAME = re.compile(r'^.*\n\s*(.*)\s*$', re.DOTALL)
RE_COMMA = re.compile(r'\s*,\s*', re.DOTALL)

logger = logging.getLogger(__name__)


class SyncState(Enum):
    GET_PRODUCTS_SUCCESS = 1
    GET_PRODUCTS_FAILED = 2
    MAIN_SUCCESS = 3
    MAIN_FAILED = 4
    PHOTO_SUCCESS = 5
    PHOTO_FAILED = 6


class SyncService:
    def __init__(self, cml_client: CmlClient, cml_url: str, cml_login: str, cml_password: SecretStr,
                 vk_client: VkClient, vk_token: SecretStr, vk_group_id: int) -> None:
        self.__cml_client = cml_client
        self.__cml_url = cml_url
        self.__cml_login = cml_login
        self.__cml_password = cml_password
        self.__vk_client = vk_client
        self.__vk_token = vk_token
        self.__vk_group_id = vk_group_id

    async def sync(
            self, with_disabled: bool = False, with_photos: bool = False,
            skip_multiple_group: bool = False, make_csv: bool = False
    ) -> AsyncIterator[tuple[SyncState, str | int | None]]:
        vk_client = await self.__vk_client.get_session(self.__vk_token)
        try:
            market = await vk_client.get_market(-self.__vk_group_id, with_disabled)
        except Exception as exc:
            logger.exception('Get products failure: %s', exc)
            yield SyncState.GET_PRODUCTS_FAILED, str(exc)
            return
        yield SyncState.GET_PRODUCTS_SUCCESS, len(market)
        groups: set[Group] = {Group(id='продано', name='Продано'), Group(id='new', name='new')}
        properties: set[Property] = set()
        products: list[Product] = []
        offers: list[Offer] = []
        csv_writer: CsvWriter | None = CsvWriter() if make_csv else None
        for item in market:
            group_id = item.owner_info.category.lower().replace(' ', '_')
            group_name = item.owner_info.category
            external_id = f'vk_{item.id}'
            groups.add(Group(id=group_id, name=item.owner_info.category))
            property_values: list[PropertyValue] = []
            description = item.description
            full_name = ''
            if properties_area_match := RE_PROPERTIES_AREA.match(description):
                description = properties_area_match.group(1)
                if properties_found := RE_PROPERTIES.findall(properties_area_match.group(2)):
                    for name, values in properties_found:
                        property_id = name.lower().replace(' ', '_')
                        properties.add(Property(id=property_id, name=name))
                        if not full_name:
                            full_name = f'{name} {values}'
                        for value in RE_COMMA.split(values):
                            property_values.append(PropertyValue(id=property_id, value=value))
            seo_descr = description.split('\n', maxsplit=1)[0]
            if not full_name and (full_name_match := RE_FULL_NAME.match(description)):
                full_name = full_name_match.group(1)
            video_urls: list[str] = []
            for video in item.videos:
                url = f'https://vk.com/video{item.owner_id}_{video.id}'
                video_urls.append(
                    f'<a href="{url}" target="_blank">Видео "{video.title}" ({timedelta(seconds=video.duration)})</a>')
            if video_urls:
                description += '\n\n' + '\n'.join(video_urls)
            new = item.date > datetime.now(UTC) - timedelta(days=31) if item.date else False
            mark: str | None = None
            if item.availability == vk_models.Availability.PRESENTED:
                title = item.title
                if new:
                    group_ids = ['new', group_id] if not skip_multiple_group else []
                    categories = ['new', group_name]
                    mark = 'NEW'
                else:
                    group_ids = [group_id]
                    categories = [group_name]
            else:
                title = f'{item.title} [Продано]'
                group_ids = ['продано']
                categories = ['Продано']
            if csv_writer:
                csv_writer.write_row(external_id, categories=categories, mark=mark, seo_descr=seo_descr)
            detail_values: list[DetailValue] = [
                DetailValue(name='SEO описание', value=seo_descr),
            ]
            if full_name:
                detail_values.append(DetailValue(name='Полное наименование', value=full_name))
            if mark:
                detail_values.append(DetailValue(name='Отметка на карточке', value=mark))
            products.append(Product(
                id=external_id,
                number=item.sku,
                name=title,
                description=description,
                group_ids=group_ids,
                images=[],
                property_values=property_values,
                detail_values=detail_values,
            ))
            offers.append(Offer(
                id=external_id,
                number=item.sku,
                name=title,
                prices=[
                    Price(price_type_id='sale_price', unit_price=item.price.old_amount / Decimal(100)),
                    Price(price_type_id='discount_price', unit_price=item.price.amount / Decimal(100))
                ] if item.price.old_amount is not None else [
                    Price(price_type_id='sale_price', unit_price=item.price.amount / Decimal(100)),
                ],
                quantity=Decimal(1) if item.availability == vk_models.Availability.PRESENTED else Decimal(0),
            ))

        classifier = CatalogClassifier(groups=list(groups), properties=list(properties))
        import_document = ImportDocument(
            classifier=classifier,
            catalog=Catalog(products=products),
        )
        offers_document = OffersDocument(
            package_of_offers=PackageOfOffers(
                price_types=[
                    PriceType(id='sale_price', name='Цена продажи'),
                    PriceType(id='discount_price', name='Цена со скидкой'),
                ],
                offers=offers,
            )
        )
        cml_client_session = await self.__cml_client.get_session(self.__cml_url, self.__cml_login, self.__cml_password)
        try:
            await cml_client_session.upload(import_document, offers_document)
        except Exception as exc:
            logger.exception('Main sync failure: %s', exc)
            yield SyncState.MAIN_FAILED, str(exc)
            return

        yield SyncState.MAIN_SUCCESS, csv_writer.finish() if csv_writer else None
        if not with_photos:
            return

        images_document = ImportDocument(
            classifier=classifier,
            catalog=Catalog(
                only_changes=True,
                products=[],
            ),
        )
        photos: dict[str, bytes] = {}
        for item in market:
            if item.availability != vk_models.Availability.PRESENTED:
                continue
            logger.info('Product photo upload: %s [%d]', item.title, item.id)
            item_photos = await vk_client.download_photos(item.photos, max_width=807)
            images_document.catalog.products.append(
                Product(
                    id=f'vk_{item.id}',
                    name=item.title,
                    images=list(item_photos),
                )
            )
            photos.update(item_photos)
        try:
            await cml_client_session.upload(import_document=images_document, photos=photos)
        except Exception as exc:
            logger.exception('Photo sync failure: %s', exc)
            yield SyncState.PHOTO_FAILED, str(exc)
            return
        yield SyncState.PHOTO_SUCCESS, len(photos)
