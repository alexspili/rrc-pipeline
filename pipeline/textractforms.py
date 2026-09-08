#!/usr/bin/env python3
"""AnalyzeDocument Forms and Tables blocks, parsed. Build-time only.

Stage six's reader (docs/labeling-protocol-extract.md, "Box grading,
stage six"). Pure: dict in, typed structures out, no I/O and no boto3.
Coordinates come back in the same page fractions DetectDocumentText uses,
validated with the same edge tolerance DEFECTS #76 set, so everything
downstream shares one coordinate space with the stage-five machinery.

The response's VALUE text is filled content and never belongs in a
committed artifact; callers that print or persist should reach for the
geometry and the KEY text (printed labels) and leave value text in the
git-ignored cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.textractwords import TextractShape, _ratio

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class KeyValue:
    """One detected form field: printed label, filled value, both boxes."""

    key_text: str
    key_box: Box
    value_text: str | None
    value_box: Box | None


@dataclass(frozen=True)
class Cell:
    row: int
    column: int
    box: Box
    text: str


@dataclass(frozen=True)
class Table:
    box: Box
    cells: tuple[Cell, ...]

    @property
    def rows(self) -> int:
        return max((c.row for c in self.cells), default=0)


def _box(block) -> Box:
    try:
        raw = block["Geometry"]["BoundingBox"]
    except (KeyError, TypeError):
        raise TextractShape(
            f"{block.get('BlockType')} block without a bounding box")
    left = _ratio("Left", raw.get("Left"))
    top = _ratio("Top", raw.get("Top"))
    right = _ratio("Left+Width", left + raw.get("Width", -1.0))
    bottom = _ratio("Top+Height", top + raw.get("Height", -1.0))
    if right <= left or bottom <= top:
        raise TextractShape(f"degenerate {block.get('BlockType')} box")
    return (left, top, right, bottom)


def _blocks_by_id(response: dict) -> dict:
    blocks = response.get("Blocks")
    if not isinstance(blocks, list):
        raise TextractShape("no Blocks list in response")
    return {b["Id"]: b for b in blocks if "Id" in b}


def _children(block, by_id, relation: str):
    for rel in block.get("Relationships", []) or []:
        if rel.get("Type") == relation:
            for block_id in rel.get("Ids", []):
                child = by_id.get(block_id)
                if child is not None:
                    yield child


def _text(block, by_id) -> str:
    words = []
    for child in _children(block, by_id, "CHILD"):
        if child.get("BlockType") == "WORD" and child.get("Text"):
            words.append(child["Text"])
        elif child.get("BlockType") == "SELECTION_ELEMENT":
            words.append(f"[{child.get('SelectionStatus', '?')}]")
    return " ".join(words)


def key_values(response: dict) -> list[KeyValue]:
    """Every detected KEY with its linked VALUE, in document order."""
    by_id = _blocks_by_id(response)
    out = []
    for block in response["Blocks"]:
        if block.get("BlockType") != "KEY_VALUE_SET":
            continue
        if "KEY" not in (block.get("EntityTypes") or []):
            continue
        value_block = next(_children(block, by_id, "VALUE"), None)
        value_box = value_text = None
        if value_block is not None:
            value_box = _box(value_block)
            value_text = _text(value_block, by_id) or None
        out.append(KeyValue(key_text=_text(block, by_id),
                            key_box=_box(block),
                            value_text=value_text, value_box=value_box))
    return out


def tables(response: dict) -> list[Table]:
    by_id = _blocks_by_id(response)
    out = []
    for block in response["Blocks"]:
        if block.get("BlockType") != "TABLE":
            continue
        cells = []
        for child in _children(block, by_id, "CHILD"):
            if child.get("BlockType") != "CELL":
                continue
            cells.append(Cell(row=int(child["RowIndex"]),
                              column=int(child["ColumnIndex"]),
                              box=_box(child), text=_text(child, by_id)))
        out.append(Table(box=_box(block), cells=tuple(cells)))
    return out
