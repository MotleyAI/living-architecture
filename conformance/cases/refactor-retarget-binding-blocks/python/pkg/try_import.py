try:
    from pkg.compat import CONST, AcmeModel
except ImportError:
    raise

a = CONST, AcmeModel()
