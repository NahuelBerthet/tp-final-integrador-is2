"""Punto de entrada CLI para observerclient."""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from tp_final_integrador_is2.observerclient import main

    sys.exit(main())
