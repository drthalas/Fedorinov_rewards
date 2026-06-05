from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence


class SaveDialogError(RuntimeError):
    pass


class SaveDialogCancelled(SaveDialogError):
    pass


SavePathChooser = Callable[[str, str, Sequence[tuple[str, str]]], str | None]


def choose_save_path(
    *,
    default_filename: str,
    title: str,
    filetypes: Sequence[tuple[str, str]],
    chooser: SavePathChooser | None = None,
) -> Path:
    selected = chooser(default_filename, title, filetypes) if chooser else _tkinter_save_path(default_filename, title, filetypes)
    if not selected:
        raise SaveDialogCancelled("Сохранение отменено.")
    return Path(selected).expanduser().resolve()


def _tkinter_save_path(default_filename: str, title: str, filetypes: Sequence[tuple[str, str]]) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise SaveDialogError("Системный диалог сохранения недоступен.") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        return filedialog.asksaveasfilename(
            title=title,
            initialfile=default_filename,
            filetypes=list(filetypes),
            defaultextension=Path(default_filename).suffix,
        )
    except Exception as exc:
        raise SaveDialogError("Не удалось открыть системный диалог сохранения.") from exc
    finally:
        root.destroy()
