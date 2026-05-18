"""Loader to import _util directly without triggering circular imports."""

import importlib.util
import pathlib

_util_path = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "iatb"
    / "selection"
    / "_util.py"
)
spec = importlib.util.spec_from_file_location("_util", str(_util_path))
_util_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]
spec.loader.exec_module(_util_mod)  # type: ignore[union-attr]
