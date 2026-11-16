from pkg.flight import (
    FlightCatalog,  # the catalog
    FlightSchema,
    FlightTable,
)


def handle() -> object:
    return FlightCatalog(), FlightSchema(), FlightTable()
