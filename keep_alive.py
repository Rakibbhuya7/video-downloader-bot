from flask import Flask, jsonify
import threading
import logging
import os
from datetime import datetime, timezone

app = Flask(__name__)

logging.getLogger("werkzeug").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

_start_time = datetime.now(timezone.utc)


# ─── /ping must be the very first route ───────────────────────────────────────

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200


@app.route("/health", methods=["GET"])
def health():
    uptime = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    return jsonify(status="ok", bot="running", uptime_seconds=uptime)


@app.route("/", methods=["GET"])
def index():
    uptime_s = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    h, rem   = divmod(uptime_s, 3600)
    m, s     = divmod(rem, 60)
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>YT Bot — Status</title>
  <style>
    body {{
      margin: 0; font-family: system-ui, sans-serif;
      background: #0d1117; color: #e6edf3;
      display: flex; align-items: center;
      justify-content: center; height: 100vh;
    }}
    .card {{
      background: #161b22; border: 1px solid #30363d;
      border-radius: 14px; padding: 2.5rem 3rem;
      text-align: center; max-width: 400px; width: 90%;
    }}
    .badge {{
      display: inline-flex; align-items: center; gap: 7px;
      background: #122112; border: 1px solid #3fb950;
      border-radius: 20px; padding: 4px 14px;
      font-size: .85rem; color: #3fb950; margin-bottom: 1.2rem;
    }}
    .dot {{
      width: 8px; height: 8px; border-radius: 50%;
      background: #3fb950; animation: blink 2s infinite;
    }}
    @keyframes blink {{ 0%,100%{{opacity:1}} 50%{{opacity:.25}} }}
    h1 {{ font-size: 1.5rem; margin-bottom: .4rem; }}
    p  {{ color: #8b949e; font-size: .9rem; margin: .3rem 0; }}
    hr {{ border: none; border-top: 1px solid #30363d; margin: 1.2rem 0; }}
    code {{
      display: block; background: #0d1117; border-radius: 6px;
      padding: 5px 12px; font-size: .8rem; color: #79c0ff; margin: 4px 0;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge"><span class="dot"></span> ONLINE</div>
    <h1>🎬 YT Downloader Bot</h1>
    <p>Pyrogram MTProto · yt-dlp</p>
    <hr>
    <p>Uptime: <strong>{h:02d}:{m:02d}:{s:02d}</strong></p>
    <p>Started: <strong>{_start_time.strftime('%Y-%m-%d %H:%M UTC')}</strong></p>
    <hr>
    <code>GET /ping   → pong</code>
    <code>GET /health → JSON</code>
  </div>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# ─── Launcher ─────────────────────────────────────────────────────────────────

def start():
    port = int(os.environ.get("PORT", 8080))
    log.info("Keep-alive server → http://0.0.0.0:%d", port)
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False),
        daemon=True,
        name="KeepAliveServer",
    )
    thread.start()
