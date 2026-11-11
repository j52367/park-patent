"""Skill docs and README must only mention `park` subcommands and flags that exist.

Skills are Markdown that an LLM follows literally, so a renamed flag silently breaks the workflow.
This test reads every `park ...` command in skills/**/*.md and README*.md and checks it against
the real argparse parser.
"""
import argparse
import re
from pathlib import Path

from park.cli import build_parser

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted((ROOT / "skills").rglob("*.md")) + sorted(ROOT.glob("README*.md"))
CMD = re.compile(r"(?<![\w/-])park\s+([a-z][a-z-]*)((?:[ \t]+[^\n`|]*)?)")


def _subparsers() -> dict[str, argparse.ArgumentParser]:
    p = build_parser()
    action = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


def _commands():
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        for m in CMD.finditer(text):
            yield doc.relative_to(ROOT), m.group(1), m.group(2) or ""


def test_docs_only_use_existing_subcommands_and_flags():
    subs = _subparsers()
    problems = []
    seen = 0
    for doc, sub, rest in _commands():
        if sub not in subs:
            # prose such as "park 도구" or "park 명령" is not a command
            if re.fullmatch(r"[a-z-]+", sub) and sub not in {"patent"}:
                problems.append(f"{doc}: unknown subcommand 'park {sub}'")
            continue
        seen += 1
        known = {o for a in subs[sub]._actions for o in a.option_strings}
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", rest):
            if flag not in known:
                problems.append(f"{doc}: 'park {sub}' has no option {flag}")
    assert seen > 20, "expected to find many park commands in the docs"
    assert not problems, "\n".join(problems)


def test_every_subcommand_is_documented_somewhere():
    documented = {sub for _, sub, _ in _commands()}
    missing = sorted(set(_subparsers()) - documented)
    assert not missing, f"subcommands not mentioned in README or any skill: {missing}"
