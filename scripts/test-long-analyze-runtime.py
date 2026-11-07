#!/usr/bin/env python3
"""단일 상태 장편 분석 런타임 테스트의 안정적인 진입점."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("test-long-analyze-runtime-refactor.py")),
        run_name="__main__",
    )
