import os

class Box:
    size = 1
    for i in range(3):
        size += i

def area(box: Box) -> int:
    return box.size * os.cpu_count()
