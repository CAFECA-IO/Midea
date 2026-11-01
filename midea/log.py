import logging
import os

_FMT = "%(asctime)s %(levelname).1s [%(name)s] %(message)s"
logging.basicConfig(level=os.environ.get("MIDEA_LOG", "INFO"), format=_FMT, datefmt="%H:%M:%S")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"midea.{name}")
