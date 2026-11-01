"""Windows stub for ``tty``. See :mod:`termios` in this directory for the rationale.

The stdlib ``tty`` module is pure Python but starts with ``from termios import *``,
so it would pick up the stub next to this file and expose a confusing partial API.
Shadowing it explicitly keeps the failure mode obvious.
"""

from termios import _MESSAGE, _unsupported  # noqa: F401  (shared message)

setraw = _unsupported
setcbreak = _unsupported
