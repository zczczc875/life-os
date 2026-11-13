import sys
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QProcess

from lifeos.instance import SingleInstance

_SRC = Path(__file__).resolve().parents[1] / "src"
_CHILD = """
import sys
from pathlib import Path
from time import sleep

from PySide6.QtCore import QCoreApplication

sys.path.insert(0, sys.argv[1])
from lifeos.instance import SingleInstance

app = QCoreApplication(sys.argv)
app.setApplicationName("LifeOS")
instance = SingleInstance(Path(sys.argv[2]))
mode = sys.argv[3]
if mode == "delayed":
    listen = instance._server.listen

    def delayed_listen(name):
        print("binding", flush=True)
        sleep(0.4)
        return listen(name)

    instance._server.listen = delayed_listen
    instance.activate_requested.connect(app.quit)
owner = instance.acquire(activate_existing=(mode == "activate"))
print("owner" if owner else "secondary", flush=True)
if mode in {"hold", "delayed"} and owner:
    app.exec()
instance.close()
"""


@contextmanager
def child_process(database, mode):
    process = QProcess()
    process.start(sys.executable, ["-c", _CHILD, str(_SRC), str(database), mode])
    try:
        assert process.waitForStarted(5000), process.errorString()
        yield process
    finally:
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
            process.waitForFinished(5000)


def wait_for_child(qtbot, process):
    qtbot.waitUntil(lambda: process.state() == QProcess.ProcessState.NotRunning, timeout=10000)
    assert process.exitCode() == 0, process.readAllStandardError().data().decode(errors="replace")
    return process.readAllStandardOutput().data().decode().strip()


def test_manual_launch_signals_owner_in_another_process(qtbot, tmp_path):
    database = tmp_path / "lifeos.sqlite3"
    owner = SingleInstance(database)
    try:
        assert owner.acquire(activate_existing=False)
        with (
            qtbot.waitSignal(owner.activate_requested, timeout=10000),
            child_process(database, "activate") as process,
        ):
            assert wait_for_child(qtbot, process) == "secondary"
    finally:
        owner.close()


def test_login_launch_does_not_restore_the_running_window(qtbot, tmp_path):
    database = tmp_path / "lifeos.sqlite3"
    owner = SingleInstance(database)
    try:
        assert owner.acquire(activate_existing=False)
        with (
            qtbot.assertNotEmitted(owner.activate_requested, wait=100),
            child_process(database, "login") as process,
        ):
            assert wait_for_child(qtbot, process) == "secondary"
    finally:
        owner.close()


def test_other_profiles_can_run_and_closing_releases_profile(qapp, tmp_path):
    database = tmp_path / "preview" / "lifeos.sqlite3"
    first = SingleInstance(database)
    other = SingleInstance(tmp_path / "stable" / "lifeos.sqlite3")
    reopened = SingleInstance(database)
    try:
        assert first.acquire(activate_existing=False)
        assert other.acquire(activate_existing=False)
        assert not reopened.acquire(activate_existing=False)
        first.close()
        assert reopened.acquire(activate_existing=False)
    finally:
        reopened.close()
        other.close()
        first.close()


def test_recovers_lock_left_by_terminated_owner(qtbot, tmp_path):
    database = tmp_path / "lifeos.sqlite3"
    with child_process(database, "hold") as process:
        assert process.waitForReadyRead(10000), (
            process.readAllStandardError().data().decode(errors="replace")
        )
        assert process.readAllStandardOutput().data().decode().strip() == "owner"

    reopened = SingleInstance(database)
    try:
        assert reopened.acquire(activate_existing=False)
    finally:
        reopened.close()


def test_manual_launch_retries_while_owner_binds_socket(qtbot, tmp_path):
    database = tmp_path / "lifeos.sqlite3"
    secondary = SingleInstance(database)
    with child_process(database, "delayed") as process:
        assert process.waitForReadyRead(10000), (
            process.readAllStandardError().data().decode(errors="replace")
        )
        assert process.readAllStandardOutput().data().decode().strip() == "binding"
        try:
            assert not secondary.acquire(activate_existing=True)
            assert wait_for_child(qtbot, process) == "owner"
        finally:
            secondary.close()
