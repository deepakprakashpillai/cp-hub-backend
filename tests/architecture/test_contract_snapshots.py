import hashlib
import json
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint

# Importing the registry is intentional: it is the Alembic/metadata composition root.
import app.db.models as _models  # noqa: F401, E402
from app.db.base import Base
from app.main import app

OPENAPI_SHA256 = "b9ce7b68ac3e67867806671a348ad5fc071449a11919ce79721afd9319c217a3"
METADATA_SHA256 = "aad184fa2a1ea4ab07da95988b14abdb1136a1fd9e6db508a453d59eeece9ed9"
ALEMBIC_HEAD = "20260729_0029"


def _sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _metadata_contract() -> list[dict]:
    contract = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        constraints = []
        for constraint in table.constraints:
            item = {
                "kind": type(constraint).__name__,
                "name": constraint.name,
                "columns": sorted(column.name for column in constraint.columns),
            }
            if isinstance(constraint, CheckConstraint):
                item["sqltext"] = str(constraint.sqltext)
            if isinstance(constraint, ForeignKeyConstraint):
                item["targets"] = sorted(element.target_fullname for element in constraint.elements)
                item["ondelete"] = sorted(element.ondelete or "" for element in constraint.elements)
            constraints.append(item)

        indexes = [
            {
                "name": index.name,
                "unique": index.unique,
                "columns": [
                    getattr(expression, "name", str(expression)) for expression in index.expressions
                ],
                "dialect": {
                    dialect: {key: str(value) for key, value in options.items()}
                    for dialect, options in index.dialect_options.items()
                },
            }
            for index in table.indexes
        ]
        contract.append(
            {
                "name": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "type": str(column.type),
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "unique": column.unique,
                        "server_default": (
                            str(column.server_default.arg)
                            if column.server_default is not None
                            else None
                        ),
                        "foreign_keys": sorted(
                            foreign_key.target_fullname for foreign_key in column.foreign_keys
                        ),
                    }
                    for column in table.columns
                ],
                "constraints": sorted(
                    constraints,
                    key=lambda value: json.dumps(value, sort_keys=True),
                ),
                "indexes": sorted(indexes, key=lambda value: value["name"] or ""),
            }
        )
    return contract


def test_openapi_contract_is_unchanged() -> None:
    assert _sha256(app.openapi()) == OPENAPI_SHA256


def test_database_metadata_is_unchanged() -> None:
    assert _sha256(_metadata_contract()) == METADATA_SHA256


def test_alembic_head_is_unchanged() -> None:
    versions = Path("alembic/versions").glob("*.py")
    revisions = {
        path.stem.split("_", 1)[0] + "_" + path.stem.split("_", 2)[1]
        for path in versions
        if path.stem[:1].isdigit()
    }
    assert ALEMBIC_HEAD in revisions
