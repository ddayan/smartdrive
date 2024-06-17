# MIT License
#
# Copyright (c) 2024 Dezen | freedom block by block
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import multiprocessing
import socket
import select
import time

from communex._common import get_node_url
from communex.client import CommuneClient
from substrateinterface import Keypair

from smartdrive.commune.request import get_filtered_modules
from smartdrive.validator.api.middleware.sign import verify_data_signature, sign_data
from smartdrive.validator.api.middleware.subnet_middleware import get_ss58_address_from_public_key
from smartdrive.validator.models.models import ModuleType
from smartdrive.validator.network.node.client import Client
from smartdrive.validator.network.node.connection_pool import ConnectionPool
from smartdrive.validator.network.node.util import packing
from smartdrive.validator.network.node.util.message_code import MessageCode
from smartdrive.validator.network.node.utils import send_json


class Server(multiprocessing.Process):
    # TODO: Replace with production validators number
    MAX_N_CONNECTIONS = 255
    IDENTIFIER_TIMEOUT_SECONDS = 5
    TCP_PORT = 9002

    def __init__(self, bind_address: str, connection_pool: ConnectionPool, keypair: Keypair, netuid: int, mempool):
        multiprocessing.Process.__init__(self)
        self.bind_address = bind_address
        self.connection_pool = connection_pool
        self.keypair = keypair
        self.comx_client = CommuneClient(url=get_node_url())
        self.netuid = netuid
        self.mempool = mempool

    def run(self):
        server_socket = None

        try:
            # self.initialize_validators()
            # self.start_check_connections_process()
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.bind_address, self.TCP_PORT))
            server_socket.listen(self.MAX_N_CONNECTIONS)

            print("LISTEN NEW CONNECTIONS")
            while True:
                client_socket, address = server_socket.accept()
                process = multiprocessing.Process(target=self.handle_connection, args=(client_socket, address))
                process.start()

        except Exception as e:
            print(f"Server stopped unexpectedly - PID: {self.pid} - {e}")
        finally:
            if server_socket:
                server_socket.close()

    def initialize_validators(self, validators=None):
        # TODO: Each connection try in for loop should be async and we should wait for all of them
        try:
            if validators is None:
                validators = get_filtered_modules(self.comx_client, self.netuid, ModuleType.VALIDATOR)
                validators = [validator for validator in validators if validator.ss58_address != self.keypair.ss58_address]

            for validator in validators:
                validator_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    # TODO: Remove port configuration and set it fixed to self.TCP_PORT, this is only to not connect a validator node to itself
                    validator_socket.connect((validator.connection.ip, validator.connection.port + 1000))
                    body = {
                        "code": MessageCode.MESSAGE_CODE_IDENTIFIER.value,
                        "data": {"ss58_address": self.keypair.ss58_address}
                    }
                    body_sign = sign_data(body, self.keypair)
                    message = {
                        "body": body,
                        "signature_hex": body_sign.hex(),
                        "public_key_hex": self.keypair.public_key.hex()
                    }
                    send_json(validator_socket, message)
                    self.connection_pool.add_connection(validator.ss58_address, validator_socket)
                    print(f"Validator {validator.ss58_address} connected and added to the pool.")
                except Exception as e:
                    self.connection_pool.remove_connection(validator.ss58_address)
                    validator_socket.close()
                    print(f"Error connecting to validator {validator.ss58_address}: {e}")
        except Exception as e:
            print(f"Error initializing validators: {e}")

    def handle_connection(self, client_socket, address):
        try:
            # Wait IDENTIFIER_TIMEOUT_SECONDS as maximum time to get the identifier message
            ready = select.select([client_socket], [], [], self.IDENTIFIER_TIMEOUT_SECONDS)
            if ready[0]:
                identification_message = packing.receive_msg(client_socket)
                print(f"Identification message received: {identification_message}")

                signature_hex = identification_message["signature_hex"]
                public_key_hex = identification_message["public_key_hex"]
                ss58_address = get_ss58_address_from_public_key(public_key_hex)

                is_verified_signature = verify_data_signature(identification_message["body"], signature_hex, ss58_address)

                if not is_verified_signature:
                    print(f"Connection signature is not valid.")
                    client_socket.close()

                connection_identifier = identification_message["body"]["data"]["ss58_address"]
                print(f"Connection reached {connection_identifier}")

                if connection_identifier in self.connection_pool.get_identifiers():
                    print(f"Connection {connection_identifier} is already in the connection pool.")
                    client_socket.close()
                    return

                if self.connection_pool.get_remaining_capacity() == 0:
                    print(f"Connection pool is full.")
                    client_socket.close()
                    return

                validators = get_filtered_modules(self.comx_client, self.netuid, ModuleType.VALIDATOR)

                if validators:
                    is_connection_validator = next((validator for validator in validators if validator.ss58_address == connection_identifier), None)

                    if is_connection_validator:
                        if self.connection_pool.get_remaining_capacity() > 0:
                            self.connection_pool.add_connection(connection_identifier, client_socket)
                            print(f"Connection added {connection_identifier}")
                            client_receiver = Client(client_socket, connection_identifier, self.connection_pool, self.mempool)
                            client_receiver.start()
                        else:
                            print(f"No space available in the connection pool for connection {connection_identifier}.")
                            client_socket.close()
                    else:
                        print(f"Looks like connection {connection_identifier} is not a valid validator.")
                        client_socket.close()
                else:
                    print("No active validators in subnet.")
                    client_socket.close()
            else:
                print(f"No identification received from {address} within timeout.")
                client_socket.close()

        except Exception as e:
            print(f"Error handling connection: {e}")
            client_socket.close()

    def start_check_connections_process(self):
        process = multiprocessing.Process(target=self.check_connections_process)
        process.start()

    def check_connections_process(self):
        while True:
            time.sleep(10)
            print("check_connections_process")
            print("check_connections_process")
            print("check_connections_process")
            validators = get_filtered_modules(self.comx_client, self.netuid, ModuleType.VALIDATOR)
            active_ss58_addresses = {validator.ss58_address for validator in validators}
            to_remove = [ss58_address for ss58_address in self.connection_pool.get_identifiers() if ss58_address not in active_ss58_addresses]
            for ss58_address in to_remove:
                removed_connection = self.connection_pool.remove_connection(ss58_address)
                if removed_connection:
                    removed_connection.close()

            identifiers = self.connection_pool.get_identifiers()
            new_validators = [validator for validator in validators if validator.ss58_address not in identifiers and validator.ss58_address != self.keypair.ss58_address]

            print("new_validators")
            print("new_validators")
            print("new_validators")
            print(new_validators)

            self.initialize_validators(new_validators)
