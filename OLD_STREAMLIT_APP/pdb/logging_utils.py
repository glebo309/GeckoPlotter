import logging
import sys


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Configure and return a logger with the given name and level.

    The logger writes to stdout with a standardized format.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # If handlers already exist, avoid duplicate logs
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

# Usage example:
# from logging_utils import setup_logger
# log = setup_logger(__name__)
# log.info("This is an informational message.")
