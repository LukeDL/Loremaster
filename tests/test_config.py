"""Platform data-directory rules stay independent from package layout."""

from pathlib import Path

from loremaster.config import Settings, default_data_dir


def test_default_data_dir_linux_uses_xdg_location():
    result = default_data_dir(
        platform="linux",
        environ={"XDG_DATA_HOME": "/srv/user-data"},
        home=Path("/home/tester"),
    )
    assert result == Path("/srv/user-data/loremaster")


def test_default_data_dir_windows_uses_local_app_data():
    result = default_data_dir(
        platform="win32",
        environ={"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"},
        home=Path("C:/Users/Tester"),
    )
    assert result == Path(r"C:\Users\Tester\AppData\Local") / "Loremaster"


def test_data_dir_environment_override_wins(monkeypatch, tmp_path):
    configured = tmp_path / "custom-data"
    monkeypatch.setenv("LOREMASTER_DATA_DIR", str(configured))
    assert Settings().data_dir == configured
