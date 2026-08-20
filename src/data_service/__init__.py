"""A-share data service layer (raw fetch + derived indicators)."""

from .service import DataService, fetch_stock_bundle

__all__ = ["DataService", "fetch_stock_bundle"]
