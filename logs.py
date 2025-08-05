"""
Logging configuration for the Telegram bot.

This module sets up a rotating file handler for logs and also outputs
warnings and errors to the console.  Logging the ``pyrogram`` library at
WARNING level prevents the chat library from spamming debug logs.

NOTE: Do not remove credit.  Telegram: @VJ_Botz, YouTube: https://youtube.com/@Tech_VJ
"""

import logging
from logging.handlers import RotatingFileHandler

# Configure logging to write to both a file and stdout.  The file rotates
# when it grows beyond 50MB and keeps 10 backups.
logging.basicConfig(
    level=logging.INFO,  # Log INFO-level messages as well as warnings/errors
    format="%(asctime)s - %(levelname)s - %(message)s [%(filename)s:%(lineno)d]",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler("logs.txt", maxBytes=50_000_000, backupCount=10),
        logging.StreamHandler(),
    ],
)

# Reduce the noise from pyrogram.  Raising the level suppresses debug logs.
logging.getLogger("pyrogram").setLevel(logging.WARNING)

logging = logging.getLogger()
