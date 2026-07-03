import json
from pathlib import Path
from typing import Any


def read_json_file(path: str | Path) -> Any:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json_file(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def read_text_file(path: str | Path) -> str:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        return file.read()


def write_text_file(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        file.write(text)