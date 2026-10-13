#!/usr/bin/env python3
"""Persistent, context-aware terminology registry. No extraction or translation."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

from library import atomic_write, cell, timestamp

STATUSES = {"seen", "mastered", "review"}


def norm(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[‐‑–—]", "-", value)
    return " ".join(value.split())


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空文本")
    return value.strip()


def text_list(value, label, required=False):
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是文本列表")
    result = list(dict.fromkeys(nonempty(x, label) for x in value))
    if required and not result:
        raise ValueError(f"{label} 不能为空")
    return result


def vocabulary_dir(root):
    folder = root / "glossary"
    if not folder.resolve().is_relative_to(root):
        raise ValueError("词库目录不能通过符号链接越过文献库")
    for name in ("terms.json", "index.md", ".glossary.lock"):
        if (folder / name).is_symlink():
            raise ValueError("词库登记/索引/锁文件不能是符号链接")
    return folder


def papers(root):
    source = json.loads((root / "library.json").read_text(encoding="utf-8"))
    if not isinstance(source, dict) or source.get("schema_version") != 1 or not isinstance(source.get("papers"), list):
        raise ValueError("文献库格式不支持；先确认现有 library.json")
    ids = [row.get("id") for row in source["papers"] if isinstance(row, dict)]
    if len(ids) != len(source["papers"]) or any(not isinstance(x, str) or not re.fullmatch(r"P\d{4,}", x) for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("文献库编号异常")
    return set(ids)


def tokens(row):
    return {norm(row["term"]), *(norm(x) for x in row["aliases"])}


def validate(data, known):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("terms"), list):
        raise ValueError("词库格式不支持；保留原数据，停止写入")
    seen_ids = set()
    rows = []
    for row in data["terms"]:
        if not isinstance(row, dict):
            raise ValueError("词条不是对象")
        term_id = nonempty(row.get("id"), "id")
        if not re.fullmatch(r"T\d{4,}", term_id) or term_id in seen_ids:
            raise ValueError("词条编号异常或重复")
        seen_ids.add(term_id)
        for key in ("term", "sense", "chinese", "definition", "created_at", "updated_at"):
            nonempty(row.get(key), key)
        text_list(row.get("aliases"), "aliases")
        if row.get("status") not in STATUSES:
            raise ValueError("词条状态异常")
        occurrences = row.get("occurrences")
        if not isinstance(occurrences, list) or not occurrences:
            raise ValueError("词条缺少出处")
        for point in occurrences:
            if not isinstance(point, dict) or point.get("paper_id") not in known:
                raise ValueError("词条引用不存在的文献")
            nonempty(point.get("anchor"), "anchor")
            if not isinstance(point.get("context", ""), str):
                raise ValueError("context 必须是文本")
        if row.get("first_seen") != occurrences[0]:
            raise ValueError("first_seen 与最早出处不一致")
        for earlier in rows:
            if norm(earlier["sense"]) == norm(row["sense"]) and tokens(earlier) & tokens(row):
                raise ValueError("同词义下别名交叉匹配多个词条，请核实后处理")
        rows.append(row)


def load(folder, known):
    path = folder / "terms.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "updated_at": timestamp(), "terms": []}
    validate(data, known)
    return data


@contextmanager
def lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ".glossary.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("词库正在写入；稍后重试，确认无写入进程前不要清理锁")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def index(folder, data):
    lines = ["# 专业词汇库", "", "seen＝已出现；mastered＝用户确认掌握；review＝待复习。出现不等于掌握。", ""]
    for row in data["terms"]:
        lines += [f"<a id=\"{row['id']}\"></a>", f"## {row['id']} · {cell(row['term'])} · {cell(row['chinese'])}", "",
                  f"词义标签：{cell(row['sense'])}；状态：{row['status']}；别名：{cell('、'.join(row['aliases']))}", "",
                  cell(row["definition"]), "", "| 文献 | 原文位置 | 语境 |", "|---|---|---|"]
        for point in row["occurrences"]:
            lines.append(f"| {point['paper_id']} | {cell(point['anchor'])} | {cell(point.get('context', ''))} |")
        lines.append("")
    lines += [f"共 {len(data['terms'])} 个词义条目；更新时间 {data['updated_at']}（UTC）。", ""]
    atomic_write(folder / "index.md", "\n".join(lines))


def save(folder, data):
    data["updated_at"] = timestamp()
    atomic_write(folder / "terms.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    # Canonical JSON may be saved even if this rebuildable export fails.
    index(folder, data)


def batch_rows(batch, known):
    if not isinstance(batch, dict) or batch.get("paper_id") not in known:
        raise ValueError("paper_id 必须是已入库的 P 编号")
    if not isinstance(batch.get("terms"), list):
        raise ValueError("terms 必须是列表")
    result = []
    for source in batch["terms"]:
        if not isinstance(source, dict):
            raise ValueError("术语输入必须是对象")
        row = {k: nonempty(source.get(k), k) for k in ("term", "sense", "chinese", "definition")}
        row["aliases"] = text_list(source.get("aliases", []), "aliases")
        row["anchors"] = text_list(source.get("anchors"), "anchors", required=True)
        row["context"] = source.get("context", "")
        if not isinstance(row["context"], str):
            raise ValueError("context 必须是文本")
        result.append(row)
    return batch["paper_id"], result


def ingest(data, batch, known):
    paper_id, incoming = batch_rows(batch, known)
    data = deepcopy(data)
    original_ids = {row["id"] for row in data["terms"]}
    touched = []
    changed = False
    for item in incoming:
        matches = [row for row in data["terms"] if norm(row["sense"]) == norm(item["sense"]) and tokens(row) & tokens(item)]
        if len(matches) > 1:
            raise ValueError("输入别名连接多个词条；不能自动合并，请核实")
        if matches:
            row = matches[0]
        else:
            term_id = "T" + str(max([int(x["id"][1:]) for x in data["terms"]] + [0]) + 1).zfill(4)
            row = {k: item[k] for k in ("term", "sense", "chinese", "definition")}
            row.update(id=term_id, aliases=[], status="seen", first_seen=None, occurrences=[], created_at=timestamp(), updated_at=timestamp())
            data["terms"].append(row)
            changed = True
        row_changed = False
        for alias in [item["term"], *item["aliases"]]:
            if norm(alias) not in tokens(row):
                row["aliases"].append(alias)
                row_changed = True
        for anchor in item["anchors"]:
            point = {"paper_id": paper_id, "anchor": anchor, "context": item["context"]}
            if point not in row["occurrences"]:
                row["occurrences"].append(point)
                row_changed = True
        row["first_seen"] = row["occurrences"][0]
        if row_changed:
            row["updated_at"] = timestamp()
            changed = True
        if row["id"] not in touched:
            touched.append(row["id"])
    validate(data, known)
    new = [row for row in data["terms"] if row["id"] in touched and row["id"] not in original_ids]
    reused = [row for row in data["terms"] if row["id"] in touched and row["id"] in original_ids]
    return data, changed, {"paper_id": paper_id, "new_terms": new, "reused_terms": reused, "new_count": len(new), "reused_count": len(reused)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "lookup", "ingest", "status", "check", "reindex"])
    parser.add_argument("--library", required=True)
    parser.add_argument("--batch")
    parser.add_argument("--query", default="")
    parser.add_argument("--term-id")
    parser.add_argument("--status", choices=sorted(STATUSES))
    args = parser.parse_args()
    root = Path(args.library).expanduser().resolve()
    known = papers(root)
    folder = vocabulary_dir(root)
    if args.command in {"lookup", "check"}:
        data = load(folder, known)
        if args.command == "lookup":
            query = norm(args.query)
            rows = [row for row in data["terms"] if not query or query in norm(" ".join([row["term"], row["chinese"], row["sense"], *row["aliases"]]))]
            result = {"terms": rows, "count": len(rows), "exists": (folder / "terms.json").exists()}
        else:
            result = {"ok": True, "count": len(data["terms"]), "exists": (folder / "terms.json").exists()}
    else:
        with lock(folder):
            data = load(folder, known)
            if args.command == "ingest":
                if not args.batch:
                    raise ValueError("ingest 需要 --batch")
                data, changed, result = ingest(data, json.loads(Path(args.batch).read_text(encoding="utf-8")), known)
                if changed or not (folder / "terms.json").exists():
                    save(folder, data)
                result["changed"] = changed
            elif args.command == "status":
                if not args.status or not args.term_id:
                    raise ValueError("status 需要 --term-id 和 --status")
                row = next((x for x in data["terms"] if x["id"] == args.term_id), None)
                if not row:
                    raise ValueError("词条编号不存在")
                previous = row["status"]
                if previous != args.status:
                    row.setdefault("status_history", []).append({"from": previous, "to": args.status, "at": timestamp()})
                    row["status"] = args.status
                    row["updated_at"] = timestamp()
                    save(folder, data)
                result = {"id": row["id"], "status": row["status"], "previous": previous}
            else:
                if args.command == "init" and not (folder / "terms.json").exists():
                    save(folder, data)
                else:
                    index(folder, data)
                result = {"ok": True, "count": len(data["terms"])}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        sys.exit(1)
