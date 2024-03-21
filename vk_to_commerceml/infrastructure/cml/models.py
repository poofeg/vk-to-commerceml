from decimal import Decimal
from datetime import datetime, timezone
from functools import partial
from typing import Optional

from pydantic import ConfigDict
from pydantic_xml import BaseXmlModel, element, wrapped, attr


class CmlBaseModel(BaseXmlModel):
    pass


class CommercialInformation(CmlBaseModel, tag='КоммерческаяИнформация'):
    schema_version: str = attr('ВерсияСхемы', default='2.04')
    creation_date: datetime = attr('ДатаФормирования', default_factory=partial(datetime.now, timezone.utc))
    syncing_products: bool = attr('СинхронизацияТоваров', default=False)


class Group(CmlBaseModel, tag='Группа'):
    model_config = ConfigDict(frozen=True)

    id: str = element(tag='Ид')
    name: str = element(tag='Наименование')


class Property(CmlBaseModel, tag='Свойство'):
    model_config = ConfigDict(frozen=True)

    id: str = element(tag='Ид')
    name: str = element(tag='Наименование')


class CatalogClassifier(CmlBaseModel, tag='Классификатор'):
    id: str = element(tag='Ид', default='classifier')
    name: str = element(tag='Наименование', default='Классификатор (Каталог товаров)')
    groups: list[Group] = wrapped('Группы', default=[])
    properties: list[Property] = wrapped('Свойства', default=[])


class BaseUnit(CmlBaseModel, tag='БазоваяЕдиница'):
    full_name: str = attr(name='НаименованиеПолное', default='шт')
    text: str = 'шт'


class PropertyValue(CmlBaseModel, tag='ЗначенияСвойства'):
    id: str = element(tag='Ид')
    value: str = element(tag='Значение')


class DetailValue(CmlBaseModel, tag='ЗначениеРеквизита'):
    name: str = element(tag='Наименование')
    value: str = element(tag='Значение')


class Product(CmlBaseModel, tag='Товар', skip_empty=True):
    id: str = element(tag='Ид')
    number: Optional[str] = element(tag='Артикул', default=None)
    name: str = element(tag='Наименование')
    base_unit: BaseUnit = BaseUnit()
    description: Optional[str] = element(tag='Описание', default=None)
    group_ids: list[str] = wrapped('Группы', element(tag='Ид', default=[]))
    images: list[str] = element(tag='Картинка', default=[])
    property_values: list[PropertyValue] = wrapped('ЗначенияСвойств', default=[])
    detail_values: list[DetailValue] = wrapped('ЗначенияРеквизитов',  default=[])


class Catalog(CmlBaseModel, tag='Каталог'):
    only_changes: bool = attr(name='СодержитТолькоИзменения', default=False)
    id: str = element(tag='Ид', default='catalog')
    classifier_id: str = element(tag='ИдКлассификатора', default='classifier')
    name: str = element(tag='Наименование', default='Каталог товаров')
    products: list[Product] = wrapped('Товары')


class ImportDocument(CommercialInformation):
    classifier: CatalogClassifier
    catalog: Catalog


class PriceType(CmlBaseModel, tag='ТипЦены'):
    id: str = element(tag='Ид')
    name: str = element(tag='Наименование')
    currency: str = element(tag='Валюта', default='RUB')


class Price(CmlBaseModel, tag='Цена'):
    price_type_id: str = element(tag='ИдТипаЦены')
    unit_price: Decimal = element(tag='ЦенаЗаЕдиницу')
    currency: str = element(tag='Валюта', default='RUB')
    unit: str = element(tag='Единица', default='шт')
    ratio: Decimal = element(tag='Коэффициент', default=Decimal(1))


class Offer(CmlBaseModel, tag='Предложение'):
    id: str = element(tag='Ид')
    number: Optional[str] = element(tag='Артикул', default=None)
    name: str = element(tag='Наименование')
    base_unit: BaseUnit = BaseUnit()
    prices: list[Price] = wrapped('Цены', default=[])
    quantity: Optional[Decimal] = element(tag='Количество', dafault=None)


class PackageOfOffers(CmlBaseModel, tag='ПакетПредложений', skip_empty=True):
    only_changes: bool = attr(name='СодержитТолькоИзменения', default=False)
    id: str = element(tag='Ид', default='offers')
    name: str = element(tag='Наименование', default='Пакет предложений')
    catalog_id: str = element(tag='ИдКаталога', default='catalog')
    classifier_id: str = element(tag='ИдКлассификатора', default='classifier')
    price_types: list[PriceType] = wrapped('ТипыЦен', default=[])
    offers: list[Offer] = wrapped('Предложения', default=[])


class OffersDocument(CommercialInformation):
    package_of_offers: PackageOfOffers
