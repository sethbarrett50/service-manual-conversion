import lemon2pdf


def test_version_is_exposed():
    assert isinstance(lemon2pdf.__version__, str)
    assert lemon2pdf.__version__
