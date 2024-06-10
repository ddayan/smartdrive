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

from fastapi import HTTPException
from substrateinterface import Keypair
from starlette.responses import FileResponse

from communex.client import CommuneClient

from smartdrive.validator.database.database import Database


class DatabaseAPI:
    _config = None
    _key: Keypair = None
    _database: Database = None
    _comx_client: CommuneClient = None

    def __init__(self, config, key, database, comx_client):
        self._config = config
        self._key = key
        self._database = database
        self._comx_client = comx_client

    def database_version_endpoint(self):
        """
        Retrieves the current version of the database.

        Returns:
            dict: A dictionary containing the database version with the key 'version'.
                  The value is the latest version number as an integer, or None if the version
                  could not be retrieved.
        """
        return {"version": self._database.get_database_version()}

    def database_endpoint(self):
        """
           Retrieves the current version of the database as a ZIP file.

           Returns:
               FileResponse: A response containing the ZIP file with the database SQL dump, using the original file name.
                             If an error occurs during the export, raises an HTTP 500 error.
        """
        database_zip_path = self._database.export_database()
        if database_zip_path:
            return FileResponse(database_zip_path, filename="export.zip")
        else:
            raise HTTPException(status_code=500, detail="Could not export the database.")