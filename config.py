import os

BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
API_ID       = int(os.environ["TELEGRAM_API_ID"])
API_HASH     = os.environ["TELEGRAM_API_HASH"]

# File size thresholds (bytes)
PYROGRAM_LIMIT = 2 * 1024 * 1024 * 1024   # 2 GB  – Pyrogram MTProto cap
CLOUD_THRESHOLD = 2 * 1024 * 1024 * 1024  # use cloud above this

# Temp download dir
DOWNLOAD_DIR = "/tmp/yt_downloads"

# Progress bar update interval (seconds)
PROGRESS_INTERVAL = 3
