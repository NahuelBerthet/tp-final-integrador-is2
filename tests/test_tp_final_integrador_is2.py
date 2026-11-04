"""Tests for tp_final_integrador_is2."""

import pytest

from tp_final_integrador_is2.tp_final_integrador_is2 import main


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify the main entry point prints a greeting."""
    main()
    captured = capsys.readouterr()
    assert "Hello, World!" in captured.out
