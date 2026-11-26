from pkg.a import Base
from pkg.sub import foo


class Child(Base):
    def run(self):
        return foo() + 1
