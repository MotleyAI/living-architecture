import random

if random.random() < 0.5:
    DEFAULT = "drop"
else:
    DEFAULT = "edit_model"  # pyright: ignore[reportConstantRedefinition]
