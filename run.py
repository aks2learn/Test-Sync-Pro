#!/usr/bin/env python3
"""
run.py – CLI entry-point for Test-Sync-Pro.

Usage:
    python run.py --id 12345
    python run.py --id 12345 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from ado_client import ADOClient
from config import Settings
from dedup_engine import DedupEngine
from delta_analyzer import DeltaAnalyzer
from folder_manager import FolderManager
from models import GeneratedTestCase, SyncResult
from test_generator import TestGenerator

console = Console()

# ── Logging ─────────────────────────────────────────────────────────────

def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


# ── Pretty output helpers ──────────────────────────────────────────────

def _show_story(story) -> None:
    console.print(
        Panel(
            f"[bold cyan]{story.title}[/]\n\n"
            f"[dim]Priority:[/] {story.priority}  |  "
            f"[dim]State:[/] {story.state}  |  "
            f"[dim]Tags:[/] {', '.join(story.tags) or '—'}\n\n"
            f"[bold]Acceptance Criteria[/]\n{story.acceptance_criteria or '[dim]None[/]'}",
            title=f"User Story #{story.id}",
            border_style="blue",
        )
    )


def _show_plan(cases: list[GeneratedTestCase]) -> None:
    table = Table(title="Generated Test Cases", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold")
    table.add_column("Type", width=10)
    table.add_column("Pri", width=4, justify="center")
    table.add_column("Category", width=12)
    table.add_column("Tags", width=24)

    for i, tc in enumerate(cases, 1):
        table.add_row(
            str(i),
            tc.title,
            tc.test_type,
            str(tc.priority),
            tc.category,
            ", ".join(tc.tags),
        )
    console.print(table)


def _show_results(result: SyncResult) -> None:
    console.print()
    console.print(
        Panel(
            f"[green bold]Created:[/]  {len(result.created_ids)}  →  {result.created_ids or '—'}\n"
            f"[yellow bold]Updated:[/]  {len(result.updated_ids)}  →  {result.updated_ids or '—'}\n"
            f"[dim]Skipped:[/]  {result.skipped_count}\n"
            f"[blue bold]Folders:[/]  {result.folder_map}",
            title="Sync Summary",
            border_style="green",
        )
    )


# ── Core orchestration ─────────────────────────────────────────────────

def run(story_id: int, dry_run: bool = False) -> SyncResult:
    """End-to-end pipeline: Fetch → Analyze → Generate → Dedup → Push."""
    result = SyncResult(story_id=story_id)

    # ── Phase 1: Fetch ──────────────────────────────────────────────
    console.rule("[bold blue]Phase 1 · Fetch User Story")
    ado = ADOClient()
    story = ado.get_user_story(story_id)
    _show_story(story)

    existing = ado.get_linked_test_cases(story_id)
    console.print(f"  Found [cyan]{len(existing)}[/] existing linked Test Cases.\n")

    # ── Phase 2: Delta analysis ─────────────────────────────────────
    console.rule("[bold blue]Phase 2 · Delta Analysis")
    analyzer = DeltaAnalyzer(story, existing)
    delta = analyzer.compute_delta()

    if analyzer.has_existing_tests and not delta:
        console.print(
            "[green]All Acceptance Criteria already covered.[/]  Nothing to generate."
        )
        result.skipped_count = len(existing)
        return result

    if delta:
        console.print("[yellow]Uncovered criteria detected:[/]")
        console.print(delta)
    else:
        console.print("[dim]No existing tests — generating full coverage.[/]")

    # ── Phase 3: AI generation ──────────────────────────────────────
    console.rule("[bold blue]Phase 3 · Generate Test Cases")
    generator = TestGenerator()
    cases = generator.generate(story, delta_hint=delta)
    _show_plan(cases)

    if dry_run:
        console.print("\n[yellow bold]DRY RUN[/] – no changes written to ADO.")
        return result

    # ── Phase 4: De-duplication ─────────────────────────────────────
    console.rule("[bold blue]Phase 4 · De-duplication")
    dedup = DedupEngine(existing)
    paired = dedup.check_batch(cases)

    to_create: list[GeneratedTestCase] = []
    to_update: list[tuple[int, GeneratedTestCase]] = []

    for tc, dup_result in paired:
        if dup_result.is_duplicate:
            console.print(
                f"  [yellow]↻[/]  '{tc.title}' matches existing "
                f"[bold]#{dup_result.matched_id}[/] ({dup_result.score:.0%})"
            )
            to_update.append((dup_result.matched_id, tc))
        else:
            to_create.append(tc)

    console.print(
        f"\n  [green]{len(to_create)}[/] new  |  "
        f"[yellow]{len(to_update)}[/] updates  |  "
        f"[dim]{result.skipped_count}[/] skipped\n"
    )

    # ── Phase 5: Push to ADO ────────────────────────────────────────
    console.rule("[bold blue]Phase 5 · Push to Azure DevOps")

    # 5a – ensure folder structure
    folder_mgr = FolderManager(ado)
    result.folder_map = folder_mgr.setup_folders()

    id_tc_pairs: list[tuple[int, GeneratedTestCase]] = []

    # 5b – create new test cases
    for tc in to_create:
        new_id = ado.create_test_case(tc, story_id)
        result.created_ids.append(new_id)
        id_tc_pairs.append((new_id, tc))

    # 5c – update existing test cases
    for tc_id, tc in to_update:
        ado.update_test_case(tc_id, tc)
        result.updated_ids.append(tc_id)
        id_tc_pairs.append((tc_id, tc))

    # 5d – file into suites
    folder_mgr.assign_many(id_tc_pairs)

    _show_results(result)
    return result


# ── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="test-sync-pro",
        description="AI-powered BDD test-case generator for Azure DevOps.",
    )
    parser.add_argument(
        "--id",
        type=int,
        required=True,
        help="Azure DevOps User Story Work-Item ID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Generate test cases but do NOT push them to ADO.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug-level logging.",
    )
    args = parser.parse_args()

    _configure_logging(args.verbose)

    console.print(
        Panel(
            "[bold white]Test-Sync-Pro[/]  –  AI-powered BDD Test-Case Agent",
            border_style="bright_magenta",
        )
    )

    Settings.validate()

    try:
        run(args.id, dry_run=args.dry_run)
    except KeyboardInterrupt:
        console.print("\n[red]Aborted by user.[/]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[red bold]Error:[/] {exc}")
        logging.getLogger("test-sync-pro").debug("Traceback:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
