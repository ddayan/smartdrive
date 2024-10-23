#  MIT License
#
#  Copyright (c) 2024 Dezen | freedom block by block
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.

import time
from _socket import SocketType
from multiprocessing import Manager
from multiprocessing.managers import DictProxy
from typing import Optional, List

from communex.types import Ss58Address

from smartdrive.commune.models import ModuleInfo
from smartdrive.validator.node.connection.utils.lock_proxy_wrapper import LockProxyWrapper
from smartdrive.validator.node.util.exceptions import ConnectionPoolMaxSizeReached

# Warning: PING_INTERVAL_SECONDS should always be considerably less than INACTIVITY_TIMEOUT_SECONDS
PING_INTERVAL_SECONDS = 5
INACTIVITY_TIMEOUT_SECONDS = 10


class Connection:
    def __init__(self, module: ModuleInfo, socket: SocketType, ping: float):
        self.module = module
        self.socket = socket
        self.ping = ping

    def __repr__(self):
        return f"Connection(module={self.module}, socket={self.socket}, ping={self.ping})"


class ConnectionPool:

    def __init__(self, manager: Manager, cache_size):
        self._connections: DictProxy[Ss58Address, Connection] = manager.dict()
        self._cache_size = cache_size
        self._lock: LockProxyWrapper = manager.Lock()

    def get(self, identifier) -> Optional[Connection]:
        with self._lock:
            if identifier in self._connections:
                return self._connections[identifier]

        return None

    def get_all(self) -> list[Connection]:
        # Ignore the warning, the values method is returning the values not a list[tuple[_KT, _VT]]
        return self._connections.values()

    def get_identifiers(self) -> list[Ss58Address]:
        return self._connections.keys()

    def get_actives(self, identifier) -> Optional[Connection]:
        with self._lock:
            current_time = time.monotonic()

            connection = self._connections.get(identifier)
            if connection and current_time - connection.ping <= INACTIVITY_TIMEOUT_SECONDS:
                return connection

        return None

    def get_modules(self) -> List[ModuleInfo]:
        return list(map(lambda connection: connection.module, self.get_all()))

    def update_or_append(self, identifier: Ss58Address, module_info: ModuleInfo, socket: SocketType):
        with self._lock:
            connection = Connection(module_info, socket, time.monotonic())

            if identifier not in self._connections:
                if len(self._connections) <= self._cache_size:
                    self._connections[identifier] = connection
                else:
                    raise ConnectionPoolMaxSizeReached(f"Max num of connections reached {self._cache_size}")

            else:
                self._connections[identifier] = connection

    def update_ping(self, identifier):
        with self._lock:
            if identifier in self._connections:
                # The manager do not keep track on attributes but object instead
                _time = time.monotonic()
                connection = self._connections[identifier]
                connection.ping = _time
                self._connections[identifier] = connection

    def remove(self, identifier: Ss58Address) -> Optional[SocketType]:
        connection = self._connections.pop(identifier, None)
        return connection.socket if connection else None

    def remove_multiple(self, identifiers: list[Ss58Address]) -> list[SocketType]:
        sockets = []
        with self._lock:
            for identifier in identifiers:
                connection = self._connections.pop(identifier, None)
                if connection:
                    sockets.append(connection.socket)
        return sockets

    def remove_inactive(self) -> list[SocketType]:
        with self._lock:
            current_time = time.monotonic()
            connections_to_remove = [identifier for identifier, c in self._connections.items() if current_time - c.ping > INACTIVITY_TIMEOUT_SECONDS]
            sockets_to_remove = [self._connections[identifier].socket for identifier in connections_to_remove]

            for identifier in connections_to_remove:
                del self._connections[identifier]
            return sockets_to_remove
