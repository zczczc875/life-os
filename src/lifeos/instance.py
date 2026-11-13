"""Keep one running LifeOS window per local database profile."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_ACTIVATION_TIMEOUT_SECONDS = 2
_CONNECT_TIMEOUT_MS = 50


class InstanceError(RuntimeError):
    """LifeOS could not acquire or contact the profile's running instance."""


class SingleInstance(QObject):
    activate_requested = Signal()

    def __init__(self, database_path: Path) -> None:
        super().__init__()
        normalized_path = os.path.normcase(str(database_path.resolve()))
        profile = hashlib.sha256(os.fsencode(normalized_path)).hexdigest()[:32]
        self._name = f"lifeos-{profile}"
        self._lock = QLockFile(str(Path(tempfile.gettempdir()) / f"{self._name}.lock"))
        self._lock.setStaleLockTime(0)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept_activation)

    def acquire(self, *, activate_existing: bool) -> bool:
        """Return True for the owner, or contact the owner on a manual launch."""
        if self._lock.isLocked():
            return True

        deadline = monotonic() + _ACTIVATION_TIMEOUT_SECONDS
        client = QLocalSocket()
        while True:
            if self._lock.tryLock(0):
                # The lock also serializes binding on Windows, where two
                # QLocalServers can otherwise listen on the same pipe.
                QLocalServer.removeServer(self._name)
                if not self._server.listen(self._name):
                    error = self._server.errorString()
                    self.close()
                    raise InstanceError(f"无法开启 LifeOS 本地窗口通信：{error}")
                return True
            if self._lock.error() != QLockFile.LockError.LockFailedError:
                raise InstanceError("无法获取 LifeOS 的本地运行锁。")
            if not activate_existing:
                return False

            client.connectToServer(self._name)
            connected = client.waitForConnected(_CONNECT_TIMEOUT_MS)
            client.abort()
            if connected:
                return False
            if monotonic() >= deadline:
                raise InstanceError("LifeOS 已在运行，但暂时无法打开窗口。")
            # The owner may still be binding its socket or finishing shutdown.
            sleep(_CONNECT_TIMEOUT_MS / 1000)

    def _accept_activation(self) -> None:
        client = self._server.nextPendingConnection()
        if client is not None:
            client.abort()
            client.deleteLater()
            self.activate_requested.emit()

    def close(self) -> None:
        """Stop receiving requests before releasing the profile lock."""
        self._server.close()
        self._lock.unlock()
