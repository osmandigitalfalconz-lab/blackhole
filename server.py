"""BlackHole — free online video downloader (server).

Paste a public video link (YouTube, Facebook, Instagram, X, Pinterest,
Threads, Reddit, Dailymotion, Snapchat, RedNote, ...) and download it as
MP4 or MP3. Videos are fetched on demand with yt-dlp and streamed back to
the user; nothing is stored.

Run locally:
    pip install -r requirements.txt
    python server.py            # http://127.0.0.1:5000

Deploy: any host that can run Python + ffmpeg (Render, Railway, Fly.io,
a small VPS). Docker: `docker build -t blackhole . && docker run -p 5000:5000 blackhole`
"""

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import quote, urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_INFO_PER_MIN = 30
MAX_DL_PER_MIN = 10
DL_TIMEOUT_SECONDS = 600  # max time to fetch one video
TMP_ROOT = tempfile.gettempdir()

_yt_dlp_bin = shutil.which("yt-dlp")
if _yt_dlp_bin:
    YTDLP_CMD = [_yt_dlp_bin]
else:
    YTDLP_CMD = [sys.executable, "-m", "yt_dlp"]

_rate_lock = threading.Lock()
_rate_buckets = {}  # (ip, endpoint) -> [timestamps]


def _rate_limited(ip, endpoint, limit):
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets.setdefault((ip, endpoint), [])
        bucket[:] = [t for t in bucket if now - t < 60]
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False


# ---------------------------------------------------------------------------
# URL safety — only public http(s) URLs, no localhost / private networks
# ---------------------------------------------------------------------------
# Only these ranges are treated as internal. (We check explicit networks
# instead of ip.is_private: sandboxed DNS can resolve public hosts to
# addresses in the 198.18.0.0/15 benchmarking range, which is_private
# wrongly flags — that would reject every real video link.)
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),     # loopback
    ipaddress.ip_network("10.0.0.0/8"),      # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),   # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique-local
)


def is_safe_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host or host.lower() in ("localhost",):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for _family, _type, _proto, _canon, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if any(ip in net for net in _BLOCKED_NETWORKS):
            return False
    return True


def _clean_filename(name, ext):
    name = re.sub(r'[\\/:*?"<>|]', "", name or "video").strip()
    name = re.sub(r"\s+", " ", name)[:120] or "video"
    return f"{name}.{ext}"


# ---------------------------------------------------------------------------
# yt-dlp helpers
# ---------------------------------------------------------------------------
def fetch_info(url):
    """Return metadata + download options for a public video URL."""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 25,
        "retries": 2,
        # YouTube's web player bot-checks Vercel's datacenter IPs
        # ("Sign in to confirm you're not a bot"), so try the Android
        # player client first and fall back to web only if it fails.
        "extractor_args": {
            "youtube": {"player_client": ["android", "web"]},
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise ValueError("Could not fetch this link.")
    if info.get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        if not entries:
            raise ValueError("Could not fetch this link.")
        info = entries[0]
    return info


def build_options(info):
    """Curated download options: one best MP4 per height + one MP3."""
    formats = info.get("formats") or []
    heights = sorted(
        {f.get("height") for f in formats
         if f.get("vcodec") not in (None, "none") and f.get("height")},
        reverse=True,
    )
    options = []
    for h in heights[:6]:
        cands = [f for f in formats
                 if f.get("height") == h and f.get("vcodec") not in (None, "none")]
        if not cands:
            continue
        cands.sort(key=lambda x: x.get("tbr") or 0, reverse=True)
        with_audio = next((f for f in cands
                           if f.get("acodec") not in (None, "none")), None)
        best = with_audio or cands[0]
        size = best.get("filesize") or best.get("filesize_approx")
        options.append({
            "id": f"bv*[height={h}]+ba/b[height<={h}]",
            "label": f"{h}p",
            "ext": "mp4",
            "size": size,
            "kind": "video",
        })
    # Fallback: if no height-based formats were found, offer best combined.
    if not options:
        options.append({
            "id": "bv*+ba/b",
            "label": "Best quality",
            "ext": "mp4",
            "size": None,
            "kind": "video",
        })
    options.append({
        # "bestaudio" alone fails for direct files, whose only format is a
        # combined video+audio stream — fall back to the best combined
        # format and extract its audio.
        "id": "bestaudio/bv*+ba/b",
        "label": "MP3 audio",
        "ext": "mp3",
        "size": None,
        "kind": "audio",
    })
    return options


def _human_size(n):
    if not n:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<page>.html")
def static_page(page):
    if page in ("how-to", "terms", "privacy", "disclaimer"):
        return send_from_directory(app.static_folder, f"{page}.html")
    return jsonify({"error": "Not found"}), 404


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/info", methods=["POST"])
def api_info():
    ip = request.remote_addr or "unknown"
    if _rate_limited(ip, "info", MAX_INFO_PER_MIN):
        return jsonify({"error": "Too many requests. Please wait a minute."}), 429
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not is_safe_url(url):
        return jsonify({"error": "Please paste a valid public video link."}), 400
    try:
        info = fetch_info(url)
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        msg = str(exc) or "Could not fetch this link."
        if "private" in msg.lower() or "login" in msg.lower():
            msg = "Could not fetch this link. It may be private or require login."
        elif "unsupported url" in msg.lower():
            msg = "This link is not from a supported site."
        else:
            msg = "Could not fetch this link. It may be private, removed or rate-limited."
        # `detail` carries the real extractor error (truncated) so a failed
        # fetch can actually be diagnosed instead of guessing.
        print(f"[blackhole] info failed for {url}: {exc}", flush=True)
        return jsonify({"error": msg, "detail": str(exc)[:300]}), 502
    thumb = info.get("thumbnail")
    thumbs = info.get("thumbnails") or []
    if not thumb and thumbs:
        thumb = thumbs[-1].get("url")
    return jsonify({
        "title": info.get("title") or "Video",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration"),
        "thumbnail": thumb,
        "platform": info.get("extractor_key") or info.get("extractor") or "",
        "webpage_url": info.get("webpage_url") or url,
        "options": [
            {**opt, "size_human": _human_size(opt["size"])}
            for opt in build_options(info)
        ],
    })


@app.route("/api/download")
def api_download():
    ip = request.remote_addr or "unknown"
    if _rate_limited(ip, "download", MAX_DL_PER_MIN):
        return jsonify({"error": "Too many downloads. Please wait a minute."}), 429
    url = (request.args.get("url") or "").strip()
    fmt = (request.args.get("format") or "").strip()
    kind = (request.args.get("kind") or "video").strip()
    title = (request.args.get("title") or "video").strip()
    if not url or not is_safe_url(url):
        return jsonify({"error": "Please paste a valid public video link."}), 400
    if not re.fullmatch(r"[A-Za-z0-9_\-\+\[\]\*\=\.\/\:\(\)<> ]+", fmt or ""):
        return jsonify({"error": "Invalid format choice."}), 400

    workdir = tempfile.mkdtemp(prefix="blackhole-", dir=TMP_ROOT)
    try:
        out_tmpl = os.path.join(workdir, "file.%(ext)s")
        cmd = YTDLP_CMD + [
            "-f", fmt,
            "--no-playlist",
            "--no-warnings",
            "--no-progress",
            "--extractor-args", "youtube:player_client=android,web",
            "-o", out_tmpl,
        ]
        if kind == "audio":
            cmd += ["-x", "--audio-format", "mp3"]
        else:
            cmd += ["--merge-output-format", "mp4"]
        cmd.append(url)
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DL_TIMEOUT_SECONDS
        )
        files = [f for f in os.listdir(workdir)
                 if os.path.isfile(os.path.join(workdir, f))]
        if proc.returncode != 0 or not files:
            err = (proc.stderr or "").strip().splitlines()
            detail = err[-1] if err else "Download failed."
            return jsonify({"error": f"Download failed: {detail}"}), 502
        path = os.path.join(workdir, files[0])
        ext = os.path.splitext(path)[1].lstrip(".") or ("mp3" if kind == "audio" else "mp4")
        filename = _clean_filename(title, ext)
        mimetype = "audio/mpeg" if ext == "mp3" else "video/mp4"
        return send_file(
            path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Download timed out. Try a lower quality."}), 504
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Download failed: {exc}"}), 502
    finally:
        # Clean the temp dir shortly after the response is sent.
        def _cleanup():
            time.sleep(30)
            shutil.rmtree(workdir, ignore_errors=True)
        threading.Thread(target=_cleanup, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
