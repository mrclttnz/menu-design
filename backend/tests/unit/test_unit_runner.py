"""Prova che il runner pytest e il pacchetto `menu` funzionano (SL-00a)."""

import menu


def test_package_importable() -> None:
    assert menu.__doc__
