#!/usr/bin/env python3
"""Local paper registry. No network, model calls, or semantic extraction."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, unquote

SCOPES = {"fulltext", "partial", "abstract", "notes"}
TYPES = {"method", "empirical", "theory", "review", "other"}
REQUIRED_TEXT = ("title", "research_question", "method", "summary", "notes_path")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def doi(value):
    value = unquote(value.strip()).lower()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)


def arxiv(value):
    value = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", value.strip())
    value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    value = re.sub(r"\.pdf$", "", value)
    return re.sub(r"v\d+$", "", value)


def identity(row):
    if row.get("doi"):
        return "doi:" + row["doi"]
    if row.get("arxiv_id"):
        return "arxiv:" + row["arxiv_id"]
    return None


def title_key(row):
    return (re.sub(r"[\W_]+", "", row["title"].casefold()), row.get("year"))


def safe_note(root, value):
    path = Path(value)
    if path.is_absolute() or not path.parts or path.parts[0] != "notes":
        raise ValueError("notes_path 必须是库内 notes/ 下的相对路径")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to((root / "notes").resolve()) or not resolved.is_relative_to(root):
        raise ValueError("阅读卡路径不能越过文献库或使用外部符号链接")
    if not resolved.is_file():
        raise ValueError(f"阅读卡尚未保存：{value}")
    return path.as_posix()


def validate_record(data, root):
    if not isinstance(data, dict):
        raise ValueError("记录必须是 JSON 对象")
    row = dict(data)
    for key in REQUIRED_TEXT:
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"缺少非空文本字段：{key}")
    if row.get("evidence_scope") not in SCOPES:
        raise ValueError("evidence_scope 应为 fulltext/partial/abstract/notes")
    if row.get("paper_type") not in TYPES:
        raise ValueError("paper_type 应为 method/empirical/theory/review/other")
    year = row.get("year")
    if year is not None and (type(year) is not int or not 1000 <= year <= 9999):
        raise ValueError("year 应为四位整数或 null")
    for key in ("authors", "keywords", "limitations", "anchors", "related_ids"):
        if not isinstance(row.get(key, []), list) or any(not isinstance(x, str) for x in row.get(key, [])):
            raise ValueError(f"{key} 应为文本列表")
        row.setdefault(key, [])
    for key in ("doi", "arxiv_id", "version", "framework", "data", "metrics", "results"):
        if not isinstance(row.get(key, ""), str):
            raise ValueError(f"{key} 应为文本")
        row.setdefault(key, "")
    row["doi"] = doi(row["doi"])
    row["arxiv_id"] = arxiv(row["arxiv_id"])
    if row["doi"] and not re.fullmatch(r"10\.\d{4,9}/\S+", row["doi"]):
        raise ValueError("DOI 格式不合法；不确定时留空，不要猜测")
    if row["arxiv_id"] and not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})", row["arxiv_id"]):
        raise ValueError("arXiv ID 格式不合法")
    sources = row.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources 需包含至少一个实际来源")
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("locator"), str) or not source["locator"].strip():
            raise ValueError("每个 source 需要非空 locator")
        if source.get("kind") not in {"pdf", "fulltext", "abstract", "notes"}:
            raise ValueError("source.kind 应为 pdf/fulltext/abstract/notes")
    innovations = row.get("innovations", [])
    if not isinstance(innovations, list):
        raise ValueError("innovations 应为列表")
    for item in innovations:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("claim", "evidence", "assessment", "verification")):
            raise ValueError("每个创新项需包含 claim/evidence/assessment/verification 非空文本")
    row.setdefault("innovations", [])
    row["notes_path"] = safe_note(root, row["notes_path"])
    if row["evidence_scope"] == "fulltext" and not row["anchors"]:
        raise ValueError("全文记录需包含来源定位 anchors")
    for key in ("id", "created_at", "updated_at", "revisions"):
        row.pop(key, None)
    return row


def load(root):
    path = root / "library.json"
    if not path.is_file():
        raise ValueError("文献库未初始化；先运行 init")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("papers"), list):
        raise ValueError("不支持的文献库格式；停止写入，保留原文件")
    return data


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".library-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".registry.lock"
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("文献库正在被写入；稍后重试。若上次中断，确认无写入进程后再移除锁文件")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def cell(value):
    return str(value or "—").replace("\n", " ").replace("\r", " ").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def index(root, data):
    lines = ["# 文献库索引", "", "本文件由登记脚本生成；详细判断请读取各篇阅读卡。", "", "| 编号 | 题名 | 年份/版本 | 阅读范围 | 关键词 | 阅读卡 |", "|---|---|---|---|---|---|"]
    for row in data["papers"]:
        target = quote(row["notes_path"], safe="/")
        lines.append(f"| {cell(row['id'])} | {cell(row['title'])} | {cell(row.get('year'))} / {cell(row.get('version'))} | {cell(row['evidence_scope'])} | {cell('、'.join(row['keywords']))} | [阅读卡]({target}) |")
    lines += ["", f"共 {len(data['papers'])} 篇。更新时间：{data['updated_at']}（UTC）。", ""]
    atomic_write(root / "index.md", "\n".join(lines))


def save(root, data):
    data["updated_at"] = timestamp()
    # JSON is the source of truth. The index is safely rebuildable if export fails.
    atomic_write(root / "library.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    index(root, data)


def upsert(root, data, row, paper_id, distinct):
    papers = data["papers"]
    key = identity(row)
    matches = [p for p in papers if key and identity(p) == key]
    existing = None
    if paper_id:
        existing = next((p for p in papers if p["id"] == paper_id), None)
        if not existing:
            raise ValueError("指定的 paper-id 不存在")
        if matches and matches[0]["id"] != paper_id:
            raise ValueError("标识符已属于另一条目，不能合并写入")
        if identity(existing) and key and identity(existing) != key:
            raise ValueError("标识符与旧条目不一致；分别保存报告版本并使用 related_ids 关联")
    elif matches:
        existing = matches[0]
    else:
        similar = [p for p in papers if title_key(p) == title_key(row)]
        if similar and not distinct:
            raise ValueError("题名/年份疑似重复：" + ", ".join(p["id"] for p in similar) + "。核实同篇后用 --paper-id，确为不同报告用 --distinct")
    known = {p["id"] for p in papers}
    if any(x not in known or (existing and x == existing["id"]) for x in row["related_ids"]):
        raise ValueError("related_ids 必须指向库内其他已存在条目")
    now = timestamp()
    if existing:
        previous = {k: v for k, v in existing.items() if k not in {"id", "created_at", "updated_at", "revisions"}}
        if previous == row:
            return existing["id"], "unchanged"
        if existing["notes_path"] == row["notes_path"]:
            raise ValueError("修订需保存新的 notes_path，以保留旧阅读卡")
        history = list(existing.get("revisions", []))
        history.append({k: v for k, v in existing.items() if k != "revisions"})
        row.update(id=existing["id"], created_at=existing["created_at"], updated_at=now, revisions=history)
        papers[papers.index(existing)] = row
        status = "updated"
    else:
        ids = [int(p["id"][1:]) for p in papers]
        row.update(id=f"P{max(ids, default=0) + 1:04d}", created_at=now, updated_at=now, revisions=[])
        papers.append(row)
        status = "created"
    save(root, data)
    return row["id"], status


def check(root, data):
    ids, identities = set(), set()
    for row in data["papers"]:
        validate_record(row, root)
        if not re.fullmatch(r"P\d{4,}", row.get("id", "")) or row["id"] in ids:
            raise ValueError("编号格式错误或重复")
        ids.add(row["id"])
        key = identity(row)
        if key and key in identities:
            raise ValueError("存在重复 DOI/arXiv 身份")
        if key:
            identities.add(key)
        for revision in row.get("revisions", []):
            safe_note(root, revision["notes_path"])
    for row in data["papers"]:
        if any(x not in ids or x == row["id"] for x in row["related_ids"]):
            raise ValueError("无效的 related_ids 关系")


def main():
    parser = argparse.ArgumentParser(description="本地文献登记、索引与版本保留；不执行论文分析")
    parser.add_argument("command", choices=["init", "list", "upsert", "check", "reindex"])
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--paper-id")
    parser.add_argument("--distinct", action="store_true")
    parser.add_argument("--query", default="")
    args = parser.parse_args()
    root = args.library.expanduser().resolve()
    try:
        if args.command == "list":
            data = load(root)
            q = args.query.casefold()
            fields = ("id", "title", "research_question", "method", "framework", "data", "metrics", "keywords")
            rows = [p for p in data["papers"] if not q or q in " ".join(str(p.get(k, "")) for k in fields).casefold()]
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        with lock(root):
            if args.command == "init":
                for folder in ("notes", "records", "comparisons"):
                    (root / folder).mkdir(exist_ok=True)
                if (root / "library.json").exists():
                    data = load(root)
                    check(root, data)
                    index(root, data)
                else:
                    save(root, {"schema_version": 1, "updated_at": timestamp(), "papers": []})
                print(json.dumps({"status": "ready", "library": str(root)}, ensure_ascii=False))
                return
            data = load(root)
            check(root, data)
            if args.command == "upsert":
                if not args.record:
                    raise ValueError("upsert 需要 --record")
                row = validate_record(json.loads(args.record.read_text(encoding="utf-8")), root)
                paper_id, status = upsert(root, data, row, args.paper_id, args.distinct)
                print(json.dumps({"id": paper_id, "status": status}, ensure_ascii=False))
            elif args.command == "check":
                print(json.dumps({"status": "valid", "count": len(data["papers"])}, ensure_ascii=False))
            else:
                index(root, data)
                print(json.dumps({"status": "rebuilt"}))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"文献库操作失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
