"""Tests that migration env is configured for per-revision transaction isolation."""

from __future__ import annotations

import ast
import pathlib
import unittest


ENV_PY = pathlib.Path(__file__).parent.parent / "migrations" / "env.py"


class MigrationAtomicityTests(unittest.TestCase):
    """Verify transaction_per_migration=True is present in migrations/env.py."""

    def test_transaction_per_migration_is_set_in_env(self) -> None:
        """do_run_migrations must pass transaction_per_migration=True to context.configure()."""
        source = ENV_PY.read_text()
        tree = ast.parse(source)

        # Walk the AST looking for context.configure(... transaction_per_migration=True ...)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Match context.configure(...)
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "configure"):
                continue
            for kw in node.keywords:
                if kw.arg == "transaction_per_migration" and isinstance(
                    kw.value, ast.Constant
                ):
                    if kw.value.value is True:
                        found = True

        self.assertTrue(
            found,
            "migrations/env.py must call context.configure(transaction_per_migration=True). "
            "Without this, a failure in one revision rolls back all preceding revisions "
            "applied in the same run.",
        )
