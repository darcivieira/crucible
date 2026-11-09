from pathlib import Path


def resolve_benchmark_path(path: Path) -> Path:
    """Resolve current and legacy filenames without copying or rewriting user files."""
    if path.exists():
        return path
    for prefix, replacement in (("benchmark", "gabarito"), ("gabarito", "benchmark")):
        if path.name.startswith(prefix):
            alternate = path.with_name(replacement + path.name[len(prefix) :])
            if alternate.exists():
                return alternate
    return path
