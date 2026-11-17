import pkg.sql.client
from pkg.sql import client

print(pkg.sql.client.connect(), client.connect(), pkg.sql.VERSION)
