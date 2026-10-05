from pathlib import Path


def test_backend_project_lives_in_backend_directory() -> None:
    backend_root = Path(__file__).resolve().parents[2]

    assert backend_root.name == "backend"
    assert (backend_root / "pyproject.toml").is_file()
    assert (backend_root / "src" / "api" / "app.py").is_file()
    assert (backend_root / "tests").is_dir()
    assert (backend_root.parent / "frontend").is_dir()
