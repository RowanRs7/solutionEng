"""Validate the metadata, structure, and local links of course Markdown."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import unquote


REQUIRED_METADATA = {
    "title",
    "slug",
    "module",
    "stage",
    "type",
    "difficulty",
    "duration",
    "prerequisites",
    "outcomes",
    "last_reviewed",
}
REQUIRED_CORE_SECTIONS = (
    "为什么需要学习",
    "学习目标",
    "前置知识",
    "业务场景",
    "核心概念",
    "工作原理",
    "架构与选型",
    "最小示例",
    "动手实验",
    "常见错误与排查",
    "安全与生产注意事项",
    "本课总结",
    "思考题",
    "小测",
    "答案与解析",
    "延伸阅读与下一课",
)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class Issue:
    path: Path
    code: str
    message: str
    line: int | None = None


def _strip_fenced_code(text: str) -> str:
    visible_lines: list[str] = []
    inside_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not inside_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            inside_fence = True
            fence_marker = stripped[:3]
            visible_lines.append("")
            continue
        if inside_fence and stripped.startswith(fence_marker):
            inside_fence = False
            visible_lines.append("")
            continue
        visible_lines.append("" if inside_fence else line)
    return "\n".join(visible_lines)


def parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}, text

    metadata: dict[str, object] = {}
    active_list: list[str] | None = None
    for line in lines[1:closing_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and active_list is not None:
            active_list.append(stripped[2:].strip())
            continue
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            metadata[key] = raw_value.strip('"\'')
            active_list = None
        else:
            active_list = []
            metadata[key] = active_list
    return metadata, "\n".join(lines[closing_index + 1 :])


def github_anchor(heading: str) -> str:
    anchor = heading.strip().lower()
    anchor = re.sub(r"<[^>]+>", "", anchor)
    anchor = re.sub(r"[\s]+", "-", anchor)
    anchor = re.sub(r"[^\w\-\u4e00-\u9fff]", "", anchor, flags=re.UNICODE)
    return anchor


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in _strip_fenced_code(text).splitlines():
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        base_anchor = github_anchor(match.group(2))
        duplicate_index = counts.get(base_anchor, 0)
        anchor = base_anchor if duplicate_index == 0 else f"{base_anchor}-{duplicate_index}"
        counts[base_anchor] = duplicate_index + 1
        anchors.add(anchor)
    return anchors


def _line_number(text: str, fragment: str) -> int | None:
    for number, line in enumerate(text.splitlines(), start=1):
        if fragment in line:
            return number
    return None


def _target_path(source: Path, root: Path, raw_target: str) -> tuple[Path, str]:
    target, separator, anchor = unquote(raw_target).partition("#")
    if not target:
        return source, anchor
    if target.startswith("/"):
        return root / target.lstrip("/"), anchor
    return (source.parent / target).resolve(), anchor


def validate_document(path: Path, root: Path) -> list[Issue]:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_front_matter(text)
    issues: list[Issue] = []

    if not metadata:
        return [Issue(path, "metadata", "missing or malformed Front Matter", 1)]

    missing_metadata = sorted(REQUIRED_METADATA - metadata.keys())
    if missing_metadata:
        issues.append(
            Issue(path, "metadata", f"missing metadata: {', '.join(missing_metadata)}", 1)
        )

    review_date = metadata.get("last_reviewed")
    try:
        if not isinstance(review_date, str):
            raise ValueError
        date.fromisoformat(review_date)
    except ValueError:
        issues.append(
            Issue(path, "invalid-review-date", "last_reviewed must be a concrete ISO date", 1)
        )

    visible_body = _strip_fenced_code(body)
    headings = {
        match.group(2).strip()
        for line in visible_body.splitlines()
        if (match := HEADING_PATTERN.match(line))
    }
    if metadata.get("type") == "core":
        for required_heading in REQUIRED_CORE_SECTIONS:
            if required_heading not in headings:
                issues.append(
                    Issue(
                        path,
                        "missing-section",
                        f"missing required section: {required_heading}",
                    )
                )

    for match in LINK_PATTERN.finditer(visible_body):
        raw_target = next(group for group in match.groups() if group is not None).strip()
        if not raw_target or raw_target.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        target_path, anchor = _target_path(path, root, raw_target)
        if not target_path.exists():
            issues.append(
                Issue(
                    path,
                    "broken-link",
                    f"local target does not exist: {raw_target}",
                    _line_number(text, raw_target),
                )
            )
            continue
        if anchor and target_path.suffix.lower() == ".md":
            target_text = target_path.read_text(encoding="utf-8")
            if anchor not in _anchors(target_text):
                issues.append(
                    Issue(
                        path,
                        "broken-anchor",
                        f"local anchor does not exist: {raw_target}",
                        _line_number(text, raw_target),
                    )
                )
    return issues


def _markdown_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".md" else []
    return sorted(
        path
        for path in root.rglob("*.md")
        if "_templates" not in path.relative_to(root).parts
        and "superpowers" not in path.relative_to(root).parts
    )


def validate_repository(root: Path) -> list[Issue]:
    root = root.resolve()
    files = _markdown_files(root)
    issues: list[Issue] = []
    slugs: dict[str, list[Path]] = {}
    for path in files:
        issues.extend(validate_document(path, root))
        metadata, _ = parse_front_matter(path.read_text(encoding="utf-8"))
        slug = metadata.get("slug")
        if isinstance(slug, str) and slug:
            slugs.setdefault(slug, []).append(path)
    for slug, paths in slugs.items():
        if len(paths) > 1:
            for path in paths:
                issues.append(Issue(path, "duplicate-slug", f"duplicate slug: {slug}", 1))
    return sorted(issues, key=lambda issue: (str(issue.path), issue.line or 0, issue.code))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    target = Path(arguments[0] if arguments else "docs")
    if not target.exists():
        print(f"{target}:1 [broken-link] validation target does not exist")
        return 1
    root = target if target.is_dir() else Path("docs")
    issues = validate_repository(target) if target.is_dir() else validate_document(target, root)
    for issue in issues:
        line = issue.line or 1
        print(f"{issue.path}:{line} [{issue.code}] {issue.message}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
