from pkg import loose


def test_loose() -> None:
    loose.alias(measures=[])
    loose.copied(measures=[])
    loose.copy_method(measures=[])
    loose.updated(measures=[])
    loose.merged(measures=[])
    loose.plain_argument(measures=[])
    loose.returned(measures=[])
    loose.iterated(measures=[])
    loose.items(measures=[])
    loose.variable_key("x", measures=[])
    loose.rebound(measures=[])
    loose.nested(measures=[])
    loose.ping(measures=[])
    loose.pong(measures=[])
    loose.both(measures=[])
    loose.alias(**{"measures": []})
