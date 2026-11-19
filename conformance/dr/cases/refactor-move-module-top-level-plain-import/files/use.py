import dest.a

print(dest.a.func())
alias = dest.a


def late() -> int:
    return dest.a.func()
