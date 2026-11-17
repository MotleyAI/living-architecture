"""Moved to pkg.b."""
from pkg.moved import raise_moved

raise_moved("pkg.a", "pkg.b", removal="2.0")
