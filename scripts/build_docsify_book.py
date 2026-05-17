from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CN_ROOT = ROOT / "cn"
MANIFEST_PATH = ROOT / "scripts" / ".docsify-book-manifest.json"
MANIFEST_VERSION = 4
TRANSLATE_MAX_CHARS = 4200
TRANSLATE_DELAY_SECONDS = 0.35
TRANSLATE_RETRY_DELAYS = [5, 10, 20, 40, 60]
TRANSLATE_SEPARATOR = "[[[QBIT_MD_SEP]]]"
PLACEHOLDER_PREFIX = "[[QBIT_PH_"
PLACEHOLDER_SUFFIX = "]]"
BOOK_HOME = "book-home.md"

EXCLUDED_TOP_LEVEL = {
    ".git",
    "assets",
    "cn",
    "node_modules",
    "scripts",
}

EXCLUDED_FILES = {
    ".nojekyll",
    "_sidebar.md",
    BOOK_HOME,
    "index.html",
}

INLINE_PATTERNS = [
    re.compile(r"!\[[^\]]*\]\([^\)]+\)"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"\$[^$\n]+\$"),
    re.compile(r"\\\([^\n]*?\\\)"),
    re.compile(r"<[^>\n]+>"),
    re.compile(r"https?://[^\s)]+"),
]

MATH_COMMAND_REPLACEMENTS = {
    r"\开始": r"\begin",
    r"\结束": r"\end",
    r"\左": r"\left",
    r"\右": r"\right",
    r"\c点": r"\cdot",
    r"\上划线": r"\overline",
    r"\有时": r"\otimes",
}

MATH_ENV_REPLACEMENTS = {
    "b矩阵": "bmatrix",
    "案例": "cases",
    "数组": "array",
    "对齐*": "align*",
}

MATH_DELIMITER_REPLACEMENTS = {
    r"\left（": r"\left(",
    r"\right）": r"\right)",
}


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict[str, dict[str, str]]:
    if not MANIFEST_PATH.exists():
        return {"version": MANIFEST_VERSION, "markdown": {}, "assets": {}}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("version") != MANIFEST_VERSION:
        return {"version": MANIFEST_VERSION, "markdown": {}, "assets": {}}
    return manifest


def save_manifest(manifest: dict[str, dict[str, str]]) -> None:
    manifest["version"] = MANIFEST_VERSION
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def is_source_content(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if not rel.parts:
        return False
    if rel.parts[0] in EXCLUDED_TOP_LEVEL:
        return False
    if rel.name in EXCLUDED_FILES:
        return False
    return True


def iter_markdown_files(filters: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        if not is_source_content(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if filters and not any(rel.startswith(item) for item in filters):
            continue
        files.append(path)
    files.sort(key=lambda item: natural_key(item.relative_to(ROOT).as_posix()))
    return files


def iter_asset_files(filters: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".md":
            continue
        if not is_source_content(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if filters and not any(rel.startswith(item) for item in filters):
            continue
        files.append(path)
    files.sort(key=lambda item: natural_key(item.relative_to(ROOT).as_posix()))
    return files


def translate_request(text: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "en",
            "tl": "zh-CN",
            "dt": "t",
            "q": text,
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    for attempt, retry_delay in enumerate([0, *TRANSLATE_RETRY_DELAYS]):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = "".join(item[0] for item in payload[0] if item and item[0])
            time.sleep(TRANSLATE_DELAY_SECONDS)
            return translated
        except Exception:
            if attempt == len(TRANSLATE_RETRY_DELAYS):
                raise
            time.sleep(retry_delay)
    raise RuntimeError("translation request failed")


def mask_inline_markup(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}
    counter = 0

    def replace(pattern: re.Pattern[str], content: str) -> str:
        nonlocal counter

        def repl(match: re.Match[str]) -> str:
            nonlocal counter
            token = f"{PLACEHOLDER_PREFIX}{counter}{PLACEHOLDER_SUFFIX}"
            counter += 1
            placeholders[token] = match.group(0)
            return token

        return pattern.sub(repl, content)

    masked = text
    for pattern in INLINE_PATTERNS:
        masked = replace(pattern, masked)
    return masked, placeholders


def restore_placeholders(text: str, placeholders: dict[str, str]) -> str:
    restored = text
    for token, original in placeholders.items():
        restored = restored.replace(token, original)
    return restored


def normalize_math_markup(text: str) -> str:
    normalized = text
    for source, target in MATH_COMMAND_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    for source, target in MATH_ENV_REPLACEMENTS.items():
        normalized = normalized.replace(f"{{{source}}}", f"{{{target}}}")
    for source, target in MATH_DELIMITER_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    return normalized


def normalize_translated_line(source_line: str, translated_line: str) -> str:
    heading_match = re.match(r"^(\s*#+)\s+", source_line)
    if heading_match:
        body = re.sub(r"^\s*[#＃]+\s*", "", translated_line).strip()
        return f"{heading_match.group(1)} {body}" if body else heading_match.group(1)
    return translated_line


def latin_character_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z]", text))


def cjk_character_count(text: str) -> int:
    return len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text))


def file_is_mostly_cjk(text: str) -> bool:
    return cjk_character_count(text) > latin_character_count(text)


def should_translate_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if re.fullmatch(r"\|?(?:\s*:?-{3,}:?\s*\|)+\s*", stripped):
        return False
    latin_count = latin_character_count(stripped)
    if latin_count == 0:
        return False
    return cjk_character_count(stripped) <= latin_count


def translate_line_batch(lines: list[str], cache: dict[str, str]) -> list[str]:
    if not lines:
        return []

    joined = f"\n{TRANSLATE_SEPARATOR}\n".join(lines)
    if joined not in cache:
        cache[joined] = translate_request(joined)
    translated = cache[joined]
    parts = translated.split(f"\n{TRANSLATE_SEPARATOR}\n")
    if len(parts) != len(lines):
        raise RuntimeError("translation separator was not preserved")
    return parts


def flush_batch(
    translated_lines: list[str],
    pending_lines: list[str],
    pending_maps: list[dict[str, str]],
    pending_sources: list[str],
    cache: dict[str, str],
) -> None:
    if not pending_lines:
        return
    translated_batch = translate_line_batch(pending_lines, cache)
    for translated, placeholders, source_line in zip(translated_batch, pending_maps, pending_sources, strict=True):
        restored = restore_placeholders(translated, placeholders)
        translated_lines.append(normalize_translated_line(source_line, restored))
    pending_lines.clear()
    pending_maps.clear()
    pending_sources.clear()


def translate_text_block(block: str, cache: dict[str, str]) -> str:
    lines = block.splitlines(keepends=False)
    translated_lines: list[str] = []
    pending_lines: list[str] = []
    pending_maps: list[dict[str, str]] = []
    pending_sources: list[str] = []
    pending_size = 0

    for line in lines:
        if not should_translate_line(line):
            flush_batch(translated_lines, pending_lines, pending_maps, pending_sources, cache)
            translated_lines.append(line)
            pending_size = 0
            continue

        masked, placeholders = mask_inline_markup(line)
        if latin_character_count(masked) == 0:
            flush_batch(translated_lines, pending_lines, pending_maps, pending_sources, cache)
            translated_lines.append(line)
            pending_size = 0
            continue

        projected_size = pending_size + len(masked) + len(TRANSLATE_SEPARATOR) + 2
        if pending_lines and projected_size > TRANSLATE_MAX_CHARS:
            flush_batch(translated_lines, pending_lines, pending_maps, pending_sources, cache)
            pending_size = 0

        pending_lines.append(masked)
        pending_maps.append(placeholders)
        pending_sources.append(line)
        pending_size += len(masked) + len(TRANSLATE_SEPARATOR) + 2

    flush_batch(translated_lines, pending_lines, pending_maps, pending_sources, cache)
    translated = "\n".join(translated_lines)
    if block.endswith("\n"):
        translated += "\n"
    return translated


def split_markdown(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines(keepends=True)
    blocks: list[tuple[str, str]] = []
    current_text: list[str] = []
    current_raw: list[str] = []
    state = "text"
    fence_marker = ""
    raw_end_marker = ""

    def flush_text() -> None:
        if current_text:
            blocks.append(("text", "".join(current_text)))
            current_text.clear()

    def flush_raw() -> None:
        if current_raw:
            blocks.append(("raw", "".join(current_raw)))
            current_raw.clear()

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if state == "fence":
            current_raw.append(line)
            if stripped.startswith(fence_marker):
                flush_raw()
                state = "text"
            continue

        if state == "raw_until_marker":
            current_raw.append(line)
            if raw_end_marker in lower:
                flush_raw()
                state = "text"
            continue

        if state == "math":
            current_raw.append(line)
            if line.count("$$") % 2 == 1:
                flush_raw()
                state = "text"
            continue

        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_text()
            current_raw.append(line)
            state = "fence"
            fence_marker = stripped[:3]
            continue

        if "$$" in line:
            flush_text()
            current_raw.append(line)
            if line.count("$$") % 2 == 1:
                state = "math"
            else:
                flush_raw()
            continue

        if lower.startswith("<style"):
            flush_text()
            current_raw.append(line)
            state = "raw_until_marker"
            raw_end_marker = "</style>"
            if raw_end_marker in lower:
                flush_raw()
                state = "text"
            continue

        if lower.startswith("<script"):
            flush_text()
            current_raw.append(line)
            state = "raw_until_marker"
            raw_end_marker = "</script>"
            if raw_end_marker in lower:
                flush_raw()
                state = "text"
            continue

        current_text.append(line)

    flush_text()
    flush_raw()
    return blocks


def translate_markdown(text: str, cache: dict[str, str]) -> str:
    translated_blocks: list[str] = []
    for kind, content in split_markdown(text):
        if kind == "raw":
            translated_blocks.append(content)
        else:
            translated_blocks.append(translate_text_block(content, cache))
    return normalize_math_markup("".join(translated_blocks))


def extract_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.startswith("＃ "):
            return stripped[2:].strip()
    stem = path.stem
    stem = re.sub(r"^\d+(?:\.\d+)*\s*", "", stem)
    return stem.strip() or path.stem


def top_level_chapter_dirs(root: Path) -> list[Path]:
    directories: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name in EXCLUDED_TOP_LEVEL:
            continue
        if (child / "index.md").exists():
            directories.append(child)
    directories.sort(key=lambda item: natural_key(item.name))
    return directories


def docsify_path(path: str) -> str:
    return urllib.parse.quote(path.replace("\\", "/"), safe="/")


def build_home_content(language: str, chapter_roots: list[Path]) -> str:
    if language == "en":
        lines = [
            "# Quantum Katas",
            "",
            "An ebook-style docsify edition of the Quantum Katas markdown collection.",
            "",
            "- Browse chapters from the sidebar.",
            "- Use the language button in the top-right corner to switch to Simplified Chinese.",
            "- Mathematical expressions render with MathJax in the reader.",
            "",
            "## Contents",
            "",
        ]
    else:
        lines = [
            "# Quantum Katas 中文版",
            "",
            "这是将 Quantum Katas Markdown 仓库整理为 docsify 电子书后的中文阅读版。",
            "",
            "- 通过左侧目录浏览章节。",
            "- 使用右上角按钮可以一键切换回英文原文。",
            "- 数学公式通过 MathJax 渲染。",
            "",
            "## 目录",
            "",
        ]

    for chapter_dir in chapter_roots:
        index_file = chapter_dir / "index.md"
        lines.append(f"- [{extract_title(index_file)}]({docsify_path(f'{chapter_dir.name}/index.md')})")

    lines.append("")
    return "\n".join(lines)


def build_sidebar(root: Path, home_label: str) -> str:
    lines = [f"* [{home_label}]({BOOK_HOME})"]
    for chapter_dir in top_level_chapter_dirs(root):
        index_file = chapter_dir / "index.md"
        if not index_file.exists():
            continue

        chapter_prefix = chapter_dir.name.split(" ", 1)[0]
        chapter_title = extract_title(index_file)
        lines.append(f"* [{chapter_prefix} {chapter_title}]({docsify_path(f'{chapter_dir.name}/index.md')})")

        section_files = [
            path
            for path in chapter_dir.glob("*.md")
            if path.name != "index.md"
        ]
        section_files.sort(key=lambda item: natural_key(item.name))
        for section_file in section_files:
            lines.append(f"  * [{extract_title(section_file)}]({docsify_path(f'{chapter_dir.name}/{section_file.name}')})")

    lines.append("")
    return "\n".join(lines)


def ensure_translated_markdown(files: list[Path], manifest: dict[str, dict[str, str]], force: bool) -> None:
    cache: dict[str, str] = {}
    for source in files:
        rel = source.relative_to(ROOT).as_posix()
        source_text = source.read_text(encoding="utf-8")
        digest = sha256_text(source_text)
        target = CN_ROOT / source.relative_to(ROOT)

        if not force and manifest["markdown"].get(rel) == digest and target.exists():
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == "README.md" or file_is_mostly_cjk(source_text):
            translated = source_text
        else:
            translated = translate_markdown(source_text, cache)
        translated = normalize_math_markup(translated)
        target.write_text(translated, encoding="utf-8")
        manifest["markdown"][rel] = digest
        save_manifest(manifest)
        print(f"translated {rel}")


def ensure_assets(files: list[Path], manifest: dict[str, dict[str, str]]) -> None:
    for source in files:
        rel = source.relative_to(ROOT).as_posix()
        digest = sha256_file(source)
        target = CN_ROOT / source.relative_to(ROOT)

        if manifest["assets"].get(rel) == digest and target.exists():
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest["assets"][rel] = digest
        save_manifest(manifest)
        print(f"copied {rel}")


def write_support_files() -> None:
    english_dirs = top_level_chapter_dirs(ROOT)
    chinese_dirs = top_level_chapter_dirs(CN_ROOT)

    (ROOT / BOOK_HOME).write_text(build_home_content("en", english_dirs), encoding="utf-8")
    (ROOT / "_sidebar.md").write_text(build_sidebar(ROOT, "Quantum Katas"), encoding="utf-8")

    CN_ROOT.mkdir(parents=True, exist_ok=True)
    (CN_ROOT / BOOK_HOME).write_text(build_home_content("zh", chinese_dirs), encoding="utf-8")
    (CN_ROOT / "_sidebar.md").write_text(build_sidebar(CN_ROOT, "Quantum Katas 中文版"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate docsify-ready English and Chinese book assets.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional relative file or directory prefixes to process. Useful for dry-running a small slice.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate matching markdown files even if the manifest says they are up to date.",
    )
    return parser.parse_args()


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> int:
    configure_stdio()
    args = parse_args()
    manifest = load_manifest()
    filters = [item.replace("\\", "/").strip("/") for item in args.paths if item.strip()]

    markdown_files = iter_markdown_files(filters)
    asset_files = iter_asset_files(filters)

    if not markdown_files and not asset_files:
        print("No matching source files found.")
        return 1

    ensure_translated_markdown(markdown_files, manifest, args.force)
    ensure_assets(asset_files, manifest)
    write_support_files()
    save_manifest(manifest)
    print("docsify book content generated")
    return 0


if __name__ == "__main__":
    sys.exit(main())