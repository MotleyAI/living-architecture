from unittest import mock
from unittest.mock import AsyncMock, MagicMock, Mock, NonCallableMock, create_autospec, patch

a = Mock()
b = MagicMock(spec=int)
c = AsyncMock(spec_set=int)
d = NonCallableMock()
e = mock.MagicMock()
f = create_autospec(int)


@patch('x.y')
def t1(m):
    pass


@patch('x.y', autospec=True)
def t2(m):
    pass


def t3():
    with patch('x.y', 1):
        pass
    with mock.patch('x.y'):
        pass
    with patch.object(int, 'real'):
        pass
    with patch.object(int, 'real', 1):
        pass
    with patch.object(int, 'real', new_callable=list):
        pass
    with patch.multiple(int, real=1):
        pass
    with patch.multiple(int, spec=True, real=1):
        pass
