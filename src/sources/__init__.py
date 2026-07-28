from .exchange_rates import ExchangeRatesSource
from .weather import WeatherSource
from .price_scraper import PriceScraperSource

SOURCE_REGISTRY = {
    "exchange_rates": ExchangeRatesSource,
    "weather": WeatherSource,
    "price_scraper": PriceScraperSource,
}
