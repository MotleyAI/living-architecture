from pkg.a import Base, foo


class Child(Base):
    def run(self):
        return foo() + 1
