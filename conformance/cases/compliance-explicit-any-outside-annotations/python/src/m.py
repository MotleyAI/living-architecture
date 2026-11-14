from typing import Any, Generic, TypeVar, cast
T = TypeVar("T", bound=Any)
class Base(Generic[T]): ...
class C(Base[Any]): ...
Alias = dict[str, Any]
y = cast(Any, 1)
z = list[Any]()
print(Any)
