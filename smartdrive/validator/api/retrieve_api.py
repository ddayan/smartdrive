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

import time
import uuid
from typing import Optional, List
from fastapi import HTTPException, Request
from substrateinterface import Keypair

from communex.client import CommuneClient
from communex.types import Ss58Address

from smartdrive.validator.api.middleware.sign import sign_data
from smartdrive.validator.api.middleware.subnet_middleware import get_ss58_address_from_public_key
from smartdrive.validator.api.utils import get_miner_info_with_chunk
from smartdrive.validator.database.database import Database
from smartdrive.commune.request import get_active_miners, execute_miner_request, ModuleInfo, ConnectionInfo
from smartdrive.models.event import RetrieveEvent, MinerProcess, EventParams, RetrieveInputParams
from smartdrive.validator.network.network import Network


class RetrieveAPI:
    _config = None
    _key: Keypair = None
    _database: Database = None
    _comx_client: CommuneClient = None
    _network: Network = None

    def __init__(self, config, key, database, comx_client, network: Network):
        self._config = config
        self._key = key
        self._database = database
        self._comx_client = comx_client
        self._network = network

    async def retrieve_endpoint(self, request: Request, file_uuid: str):
        """
        Retrieves a file chunk from active miners.

        This method checks if a file exists for a given user SS58 address and file UUID.
        If the file exists, it proceeds to find and retrieve the corresponding chunks
        from active miners.

        Params:
            user_ss58_address (Ss58Address): The SS58 address of the user associated with the file.
            file_uuid (str): The UUID of the file to be retrieved.

        Returns:
            chunk: The retrieved file chunk if available, None otherwise.

        Raises:
            HTTPException: If the file does not exist, no miner has the chunk, or no active miners are available.
        """
        user_public_key = request.headers.get("X-Key")
        input_signed_params = request.headers.get("X-Signature")
        user_ss58_address = get_ss58_address_from_public_key(user_public_key)

        file_exists = self._database.check_if_file_exists(user_ss58_address, file_uuid)
        if not file_exists:
            print("The file not exists")
            raise HTTPException(status_code=404, detail="File does not exist")

        miner_chunks = self._database.get_miner_chunks(file_uuid)
        if not miner_chunks:
            print("Currently no miner has any chunk")
            raise HTTPException(status_code=404, detail="Currently no miner has any chunk")

        active_miners = await get_active_miners(self._key, self._comx_client, self._config.netuid)
        if not active_miners:
            print("Currently there are no active miners")
            raise HTTPException(status_code=404, detail="Currently there are no active miners")

        miners_with_chunks = get_miner_info_with_chunk(active_miners, miner_chunks)

        # Create event
        miners_processes: List[MinerProcess] = []
        # TODO: This method currently is assuming that chunks are final files. This is an early stage.
        for miner_chunk in miners_with_chunks:
            start_time = time.time()
            connection = ConnectionInfo(miner_chunk["connection"]["ip"], miner_chunk["connection"]["port"])
            miner_info = ModuleInfo(
                miner_chunk["uid"],
                miner_chunk["ss58_address"],
                connection
            )
            chunk = await retrieve_request(self._key, user_ss58_address, miner_info, miner_chunk["chunk_uuid"])
            final_time = time.time() - start_time
            miner_chunk["chunk"] = chunk

            miner_process = MinerProcess(
                chunk_uuid=miner_chunk["chunk_uuid"],
                miner_ss58_address=miner_chunk["ss58_address"],
                succeed=chunk is not None,
                processing_time=final_time
            )
            miners_processes.append(miner_process)

        event_params = EventParams(
            file_uuid=file_uuid,
            miners_processes=miners_processes,
        )

        signed_params = sign_data(event_params.dict(), self._key)

        event = RetrieveEvent(
            uuid=f"{int(time.time())}_{str(uuid.uuid4())}",
            validator_ss58_address=Ss58Address(self._key.ss58_address),
            event_params=event_params,
            event_signed_params=signed_params.hex(),
            user_ss58_address=user_ss58_address,
            input_params=RetrieveInputParams(file_uuid=file_uuid),
            input_signed_params=input_signed_params
        )

        # Emit event
        self._network.emit_event(event)

        if miners_with_chunks[0]["chunk"]:
            return miners_with_chunks[0]["chunk"]
        else:
            print("The chunk does not exists")
            raise HTTPException(status_code=404, detail="The chunk does not exist")


async def retrieve_request(keypair: Keypair, user_ss58address: Ss58Address, miner: ModuleInfo, chunk_uuid: str) -> Optional[str]:
    """
    Sends a request to a miner to retrieve a specific data chunk.

    This method sends an asynchronous request to a specified miner to retrieve a data chunk
    identified by its UUID. The request is executed using the miner's connection and
    address information.

    Params:
        keypair (Keypair): The validator key used to authorize the request.
        user_ss58_address (Ss58Address): The SS58 address of the user associated with the data chunk.
        miner (ModuleInfo): The miner's module information.
        chunk_uuid (str): The UUID of the data chunk to be retrieved.

    Returns:
        Optional[str]: Returns the chunk UUID, or None if something went wrong.
    """
    miner_answer = await execute_miner_request(
        keypair, miner.connection, miner.ss58_address, "retrieve",
        {
            "folder": user_ss58address,
            "chunk_uuid": chunk_uuid
        }
    )

    return miner_answer["chunk"] if miner_answer else None
