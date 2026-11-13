import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def external_python(tmp_path):
    env_dir = tmp_path / "worker venv"
    subprocess.run([sys.executable, "-m", "venv", "--copies", "--without-pip", str(env_dir)], check=True)
    if sys.platform == "win32":
        site = env_dir / "Lib/site-packages"
        executable = env_dir / "Scripts/python.exe"
    else:
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site = env_dir / "lib" / version / "site-packages"
        executable = env_dir / "bin/python"
    dependency_paths = [path for path in sys.path if Path(path).name == "site-packages"]
    (site / "test_dependencies.pth").write_text("\n".join(dependency_paths) + "\n", encoding="utf-8")
    return str(executable)


@pytest.fixture
def stub_worker_cli(monkeypatch, external_python):
    real_popen = subprocess.Popen

    def configure(script):
        def launch(args, *rest, **kwargs):
            if args[:3] == [external_python, "-m", "ai.worker"]:
                args = [external_python, str(script), *args[3:]]
            return real_popen(args, *rest, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", launch)
        return external_python

    return configure
