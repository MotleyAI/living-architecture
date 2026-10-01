from pkg.a import Base, foo


class Child(Base):
    def execute(self):
        return foo() + 1
