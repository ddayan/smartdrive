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

import base64
import os
import tempfile
import zipfile
from typing import Optional
import requests

from smartdrive.commune.request import ConnectionInfo


def extract_sql_file(zip_filename: str) -> Optional[str]:
    """
    Extracts the SQL file from the given ZIP archive and stores it in a temporary file.

    Params:
        zip_filename (str): The path to the ZIP file that contains the SQL file.

    Returns:
        Optional[str]: The path to the temporary SQL file if extraction is successful, or None if an error occurs.
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            sql_files = [f for f in os.listdir(temp_dir) if f.endswith('.sql')]
            if not sql_files:
                print("No SQL files found in the ZIP archive.")
                return None

            sql_file_path = os.path.join(temp_dir, sql_files[0])
            temp_sql_file = tempfile.NamedTemporaryFile(delete=False, suffix='.sql')
            temp_sql_file.close()
            os.rename(sql_file_path, temp_sql_file.name)
            return temp_sql_file.name

    except Exception as e:
        print(f"Error during database import - {e}")
        return None


def fetch_validator(action: str, connection: ConnectionInfo, timeout=60) -> Optional[requests.Response]:
    """
    Sends a request to a specified validator action endpoint.

    This function sends a request to a specified action endpoint of a validator
    using the provided connection information. It handles any exceptions that may occur
    during the request and logs an error message if the request fails.

    Params:
        action (str): The action to be performed at the validator's endpoint.
        connection (ConnectionInfo): The connection information containing the IP address and port of the validator.
        timeout (int): The timeout for the request in seconds. Default is 60 seconds.

    Returns:
        Optional[requests.Response]: The response object if the request is successful, otherwise None.
    """
    try:
        response = requests.get(f"https://{connection.ip}:{connection.port}/{action}", timeout=timeout)
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Error fetching action {action} with connection {connection.ip}:{connection.port} - {e}")
        return None


def encode_bytes(data: bytes) -> str:
    """
    Encodes bytes into a base64 string.

    Params:
        data (bytes): The data to be encoded.

    Returns:
        str: The base64 encoded string.
    """
    return base64.b64encode(data).decode("utf-8")