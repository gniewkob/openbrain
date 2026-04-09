from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_gateway_module_cache: dict[str, object] = {}


def load_gateway_module(module_name: str = "main"):
    """Load a module from MCP gateway src package without polluting global 'src'.

    The gateway and the backend both use the 'src' package namespace. We load the
    gateway module under a private alias so that backend tests running in the same
    pytest session are unaffected.
    """
    cached = _gateway_module_cache.get(module_name)
    if cached is not None:
        return cached

    gateway_root = Path(__file__).resolve().parents[1]
    src_dir = gateway_root / "src"
    shared_src_dir = gateway_root.parent / "src"
    package_init = src_dir / "__init__.py"
    module_path = src_dir / f"{module_name}.py"

    if str(shared_src_dir) not in sys.path:
        sys.path.insert(0, str(shared_src_dir))

    alias = "_gateway_src"

    pkg_spec = importlib.util.spec_from_file_location(
        alias,
        package_init,
        submodule_search_locations=[str(src_dir)],
    )
    if pkg_spec is None or pkg_spec.loader is None:
        raise RuntimeError(f"Failed to load package spec for {package_init}")
    pkg = importlib.util.module_from_spec(pkg_spec)
    sys.modules[alias] = pkg
    pkg_spec.loader.exec_module(pkg)

    module_spec = importlib.util.spec_from_file_location(
        f"{alias}.{module_name}", module_path
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Failed to load module spec for {module_path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[f"{alias}.{module_name}"] = module
    module_spec.loader.exec_module(module)

    _gateway_module_cache[module_name] = module
    return module


def load_gateway_main():
    return load_gateway_module("main")
