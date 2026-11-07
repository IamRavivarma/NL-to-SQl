import json
import re

from app.sql.table_store import TableInfo

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def describe_schema(catalog: list[TableInfo], samples: dict[str, list[tuple]]) -> str:
    """The tables the model may query: columns with types and original headers, plus a few sample rows."""
    blocks = []
    for info in catalog:
        lines = [f"Table {info.table_name} (from {info.filename} p.{info.page}, {info.row_count} rows)"]
        lines += [f'  - {c["name"]} {c["type"]}  -- header "{c["original"]}"' for c in info.columns]
        for row in samples.get(info.table_name, []):
            lines.append(f"  sample: {row}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def parse_sql_plan(text: str) -> str | None:
    """The `sql` value of the JSON object in the model's reply, or None when there is no usable query."""
    match = _JSON_OBJECT.search(text)
    if not match:
        return None
    try:
        plan = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    sql = plan.get("sql") if isinstance(plan, dict) else None
    return sql.strip() or None if isinstance(sql, str) else None
