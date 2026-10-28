#!/usr/bin/env python3
"""Синхронизировать canonical prompts.json в webapp/ для статического хостинга.

Mini App читает prompts.json relative к своему собственному адресу, поэтому
в deploy-пакете webapp/ должен быть свой копия. Этот скрипт поддерживает
один источник истины (корневой prompts.json) и копирует его в webapp/.

Использование:
    python scripts/sync_prompts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "prompts.json"
DST = ROOT / "webapp" / "prompts.json"


def main() -> int:
    if not SRC.exists():
        print(f"[sync_prompts] Ошибка: не найден canonical-файл {SRC}", file=sys.stderr)
        return 1

    try:
        data = json.loads(SRC.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[sync_prompts] Ошибка: некорректный JSON в {SRC}: {exc}", file=sys.stderr)
        return 1

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    count = len(data) if isinstance(data, list) else 1
    print(f"[sync_prompts] {SRC.relative_to(ROOT)} -> {DST.relative_to(ROOT)} ({count} промпт(ов))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
