import sys


def load():
    global pa
    import pkg.a as pa


load()
print(pa.f(), sys.argv)
