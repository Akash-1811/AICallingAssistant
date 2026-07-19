"""
One logger setup for the whole app — import get_logger(__name__) everywhere.
"""
import logging

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"

)

def get_logger(name: str):

    return logging.getLogger(name)