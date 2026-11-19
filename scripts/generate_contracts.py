"""Export current Pydantic request models for openapi-typescript (no HTTP required)."""

import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yanji import contracts

schemas = {}
for name, model in inspect.getmembers(contracts, inspect.isclass):
    if model.__module__ == contracts.__name__:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[name] = schema
Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "openapi": "3.1.0",
            "info": {"title": "YanJi contracts", "version": "2.0"},
            "paths": {},
            "components": {"schemas": schemas},
        },
        ensure_ascii=False,
    )
)
