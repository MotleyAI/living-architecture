from pkg.sql.engine import connect
from .sql import VERSION

print(connect(), VERSION)
