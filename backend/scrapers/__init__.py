from .amazon import AmazonScraper
from .flipkart import FlipkartScraper
from .croma import CromaScraper
from .reliance import RelianceScraper
from .vijaysales import VijaysSalesScraper
from .base import ScrapedProduct

SCRAPERS = {
    "amazon":     AmazonScraper(),
    "flipkart":   FlipkartScraper(),
    "croma":      CromaScraper(),
    "reliance":   RelianceScraper(),
    "vijaysales": VijaysSalesScraper(),
}

__all__ = [
    "AmazonScraper", "FlipkartScraper", "CromaScraper",
    "RelianceScraper", "VijaysSalesScraper", "ScrapedProduct", "SCRAPERS",
]
#test commit