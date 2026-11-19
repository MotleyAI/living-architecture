try:
    import fast
except ImportError:
    def fast():
        return 1
import os
