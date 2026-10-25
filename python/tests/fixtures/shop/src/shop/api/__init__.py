from shop.core import place_order
from shop.store import save


def post_order(item: str) -> str:
    return place_order(item)


def post_order_fast(item: str) -> str:
    return save(item)
