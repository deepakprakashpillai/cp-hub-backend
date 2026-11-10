import importlib.util
from pathlib import Path
from unittest.mock import Mock


def test_migration_preserves_existing_roles_and_guards_downgrade(monkeypatch):
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions"
        / "20261110_0030_add_additional_user_role.py"
    )
    spec = importlib.util.spec_from_file_location("multi_role_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    op = Mock()
    monkeypatch.setattr(migration, "op", op)
    migration.upgrade()
    column = op.add_column.call_args.args[1]
    assert column.name == "additional_role"
    assert column.nullable is True
    check = op.create_check_constraint.call_args.args[2]
    assert "role = 'admin' AND additional_role = 'teacher'" in check
    assert "role = 'teacher' AND additional_role = 'admin'" in check
    op.execute.assert_not_called()
    op.reset_mock()
    migration.downgrade()
    assert "RAISE EXCEPTION" in op.method_calls[0].args[0]
    assert op.method_calls[0][0] == "execute"
    assert op.method_calls[-1][0] == "drop_column"
