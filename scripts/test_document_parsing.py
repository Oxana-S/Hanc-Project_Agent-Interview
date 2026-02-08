#!/usr/bin/env python3
"""
Stage 6.5: Тестирование парсинга документов из input/ папки.

Проверяет:
1. Все форматы парсятся (PDF, DOCX, MD, XLSX, TXT)
2. DocumentLoader загружает все файлы из каждой подпапки
3. DocumentAnalyzer создаёт контекст
4. Контекст содержит извлечённые данные (контакты, услуги, ключевые факты)
5. to_prompt_context() генерирует непустую строку

Запуск:
    python scripts/test_document_parsing.py
    python scripts/test_document_parsing.py --dir input/test_docs
    python scripts/test_document_parsing.py --verbose
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

INPUT_DIR = Path(__file__).parent.parent / "input"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".xlsx", ".xls", ".txt"}


def test_single_format(parser, file_path: Path, verbose: bool = False) -> dict:
    """Test parsing a single file."""
    result = {
        "file": file_path.name,
        "format": file_path.suffix,
        "status": "FAIL",
        "chunks": 0,
        "words": 0,
        "error": None,
    }

    try:
        doc = parser.parse(file_path)
        if doc:
            result["status"] = "OK"
            result["chunks"] = len(doc.chunks)
            result["words"] = doc.word_count

            if verbose:
                for chunk in doc.chunks[:2]:
                    preview = chunk.content[:80].replace("\n", " ")
                    console.print(f"    [dim]chunk: {preview}...[/dim]")
        else:
            result["error"] = "parse returned None"
    except Exception as e:
        result["error"] = str(e)

    return result


def test_loader(input_dir: Path, verbose: bool = False) -> dict:
    """Test DocumentLoader on a directory."""
    from src.documents import DocumentLoader

    loader = DocumentLoader()
    documents = loader.load_all(input_dir)

    result = {
        "dir": input_dir.name,
        "total_files": len(documents),
        "total_words": sum(d.word_count for d in documents),
        "formats": {},
    }

    for doc in documents:
        fmt = doc.doc_type
        if fmt not in result["formats"]:
            result["formats"][fmt] = 0
        result["formats"][fmt] += 1

    return result


def test_analyzer(input_dir: Path, verbose: bool = False) -> dict:
    """Test DocumentAnalyzer on a directory."""
    from src.documents import DocumentLoader, DocumentAnalyzer

    loader = DocumentLoader()
    documents = loader.load_all(input_dir)

    if not documents:
        return {"status": "SKIP", "reason": "no documents"}

    analyzer = DocumentAnalyzer()
    context = analyzer.analyze_sync(documents)

    result = {
        "status": "OK",
        "total_documents": context.total_documents,
        "total_words": context.total_words,
        "has_summary": bool(context.summary),
        "key_facts": len(context.key_facts),
        "services": len(context.services_mentioned),
        "contacts": len(context.all_contacts),
        "questions": len(context.questions_to_clarify),
        "prompt_context_length": len(context.to_prompt_context()),
    }

    if verbose:
        if context.all_contacts:
            console.print(f"    [dim]Contacts: {context.all_contacts}[/dim]")
        if context.services_mentioned:
            console.print(f"    [dim]Services: {context.services_mentioned[:5]}[/dim]")
        prompt_preview = context.to_prompt_context()[:200].replace("\n", " ")
        console.print(f"    [dim]Prompt: {prompt_preview}...[/dim]")

    return result


@click.command()
@click.option("--dir", "-d", "target_dir", help="Конкретная папка для тестирования")
@click.option("--verbose", "-v", is_flag=True, help="Подробный вывод")
def main(target_dir: str, verbose: bool):
    """Test document parsing for all input/ subfolders."""
    console.print(Panel(
        "[bold cyan]ТЕСТИРОВАНИЕ ПАРСИНГА ДОКУМЕНТОВ[/bold cyan]\n\n"
        "Проверка: парсинг всех форматов, загрузка, анализ",
        border_style="cyan"
    ))

    from src.documents import DocumentParser

    parser = DocumentParser()

    # Determine directories to test
    if target_dir:
        dirs = [Path(target_dir)]
    else:
        dirs = sorted([d for d in INPUT_DIR.iterdir() if d.is_dir()])

    if not dirs:
        console.print("[red]Нет папок для тестирования в input/[/red]")
        sys.exit(1)

    all_ok = True
    total_files = 0
    total_parsed = 0
    format_stats = {}

    for dir_path in dirs:
        console.print(f"\n[bold]📁 {dir_path.name}/[/bold]")

        # 1. Test individual file parsing
        files = sorted([
            f for f in dir_path.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ])

        if not files:
            console.print("  [yellow]Нет файлов для парсинга[/yellow]")
            continue

        table = Table(show_header=True, header_style="bold")
        table.add_column("Файл", width=30)
        table.add_column("Формат", width=8)
        table.add_column("Статус", width=8)
        table.add_column("Chunks", width=8, justify="right")
        table.add_column("Words", width=8, justify="right")

        for f in files:
            total_files += 1
            result = test_single_format(parser, f, verbose)

            fmt = result["format"]
            if fmt not in format_stats:
                format_stats[fmt] = {"ok": 0, "fail": 0}

            if result["status"] == "OK":
                total_parsed += 1
                format_stats[fmt]["ok"] += 1
                status_str = "[green]✅ OK[/green]"
            else:
                all_ok = False
                format_stats[fmt]["fail"] += 1
                status_str = f"[red]❌ {result['error']}[/red]"

            table.add_row(
                result["file"],
                result["format"],
                status_str,
                str(result["chunks"]),
                str(result["words"]),
            )

        console.print(table)

        # 2. Test DocumentLoader
        loader_result = test_loader(dir_path, verbose)
        formats_str = ", ".join(f"{k}:{v}" for k, v in loader_result["formats"].items())
        console.print(f"  Loader: {loader_result['total_files']} файлов, {loader_result['total_words']} слов [{formats_str}]")

        # 3. Test DocumentAnalyzer
        analyzer_result = test_analyzer(dir_path, verbose)
        if analyzer_result["status"] == "OK":
            console.print(
                f"  Analyzer: ✅ docs={analyzer_result['total_documents']}, "
                f"facts={analyzer_result['key_facts']}, "
                f"services={analyzer_result['services']}, "
                f"contacts={analyzer_result['contacts']}, "
                f"prompt={analyzer_result['prompt_context_length']} chars"
            )
        else:
            console.print(f"  Analyzer: [yellow]⚠️ {analyzer_result.get('reason', 'unknown')}[/yellow]")

    # Summary
    console.print(f"\n{'=' * 60}")
    console.print("[bold]СВОДКА[/bold]")
    console.print(f"{'=' * 60}")

    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Формат", width=10)
    summary_table.add_column("OK", width=8, justify="right")
    summary_table.add_column("FAIL", width=8, justify="right")
    summary_table.add_column("Статус", width=10)

    for fmt in sorted(format_stats.keys()):
        stats = format_stats[fmt]
        status = "[green]✅[/green]" if stats["fail"] == 0 else "[red]❌[/red]"
        summary_table.add_row(fmt, str(stats["ok"]), str(stats["fail"]), status)

    console.print(summary_table)
    console.print(f"\nВсего: {total_parsed}/{total_files} файлов распарсено")
    console.print(f"Папок: {len(dirs)}")

    if all_ok:
        console.print("\n[bold green]✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ[/bold green]")
        sys.exit(0)
    else:
        console.print("\n[bold red]❌ ЕСТЬ ОШИБКИ[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
