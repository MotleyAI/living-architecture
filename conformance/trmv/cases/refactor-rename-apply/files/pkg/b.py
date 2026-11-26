from pkg.a import Base, bar


class Child(Base):
    def run(self):
        return bar() + 1
