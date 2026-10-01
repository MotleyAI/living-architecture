from pkg.a import Base
import pkg.sub


class Child(Base):
    def run(self):
        return pkg.sub.foo() + 1
