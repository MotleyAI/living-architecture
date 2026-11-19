from pkg.kw import kwonly


def pass_on(mapping: dict[str, str]) -> str:
    return kwonly(**mapping)
