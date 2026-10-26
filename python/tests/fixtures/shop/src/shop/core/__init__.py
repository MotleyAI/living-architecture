from shop.store import save


def place_order(item: str) -> str:
    return save(item)
