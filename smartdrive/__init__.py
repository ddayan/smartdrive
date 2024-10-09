from .version import __version__, check_version  # noqa: F401
from . import cli, miner, validator  # noqa: F401
from .logging_config import logger  # noqa: F401

# TODO: Change when deploy
NETUID = 4
TESTNET_NETUID = 25
