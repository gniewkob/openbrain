from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_gateway_main_cache: object | None = None


def load_gateway_main():
    """Load the MCP gateway's src.main without polluting sys.modules for other tests.

    The gateway and the backend both use the 'src' package namespace. We load the
    gateway module under a private alias so that backend tests running in the same
    pytest session are unaffected.
    """
    global _gateway_main_cache
    if _gateway_main_cache is not None:
        return _gateway_main_cache

    gateway_root = Path(__file__).resolve().parents[1]
    src_dir = gateway_root / "src"
    shared_src_dir = gateway_root.parent / "src"
    package_init = src_dir / "__init__.py"
    main_path = src_dir / "main.py"

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

    main_spec = importlib.util.spec_from_file_location(f"{alias}.main", main_path)
    if main_spec is None or main_spec.loader is None:
        raise RuntimeError(f"Failed to load module spec for {main_path}")
    module = importlib.util.module_from_spec(main_spec)
    sys.modules[f"{alias}.main"] = module
    main_spec.loader.exec_module(module)

    _gateway_main_cache = module
    return module
