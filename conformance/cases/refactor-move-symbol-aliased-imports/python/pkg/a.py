import xml.etree.ElementTree as ET
from os import path as osp


def f() -> str:
    return ET.__name__ + osp.sep


def g() -> str:
    return osp.sep
