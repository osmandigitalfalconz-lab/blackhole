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
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
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
def _has_ffmpeg():
    """True when an ffmpeg binary is available (needed for MP3 conversion
    and for merging separate video+audio streams). Vercel's serverless
    runtime has none, so the code falls back to combined formats and
    native audio there; a normal host (Render/VPS) has it."""
    if shutil.which("ffmpeg"):
        return True
    loc = os.environ.get("FFMPEG_LOCATION")
    if loc and os.path.isfile(loc):
        return True
    try:
        import imageio_ffmpeg
        return os.path.isfile(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return False


def _ffmpeg_location():
    """Path to an ffmpeg binary, or None."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    loc = os.environ.get("FFMPEG_LOCATION")
    if loc and os.path.isfile(loc):
        return loc
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def _vimeo_fallback(url):
    """Vimeo's web client now requires a login, so yt-dlp fails. For public
    videos the player config still lists direct progressive MP4 files —
    fetch it and return a synthetic info dict built from those."""
    m = re.search(r"vimeo\.com/(?:channels/[^/]+/|groups/[^/]+/videos/|album/\d+/video/|video/|)(\d+)", url)
    if not m:
        return None
    vid = m.group(1)
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    cfg = None
    try:
        req = urllib.request.Request(
            f"https://player.vimeo.com/video/{vid}/config",
            headers={"User-Agent": ua, "Referer": f"https://vimeo.com/{vid}"},
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            cfg = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        cfg = None
    if cfg is None:
        # The config endpoint is IP-blocked on some hosts; the public
        # video page embeds the same player config JSON in its HTML.
        try:
            req = urllib.request.Request(
                f"https://vimeo.com/{vid}",
                headers={"User-Agent": ua, "Accept": "text/html"},
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                html = resp.read().decode("utf-8", "replace")
            idx = html.find('"progressive":')
            if idx >= 0:
                start = html.find("[", idx)
                arr, _ = json.JSONDecoder().raw_decode(html[start:])
                title_m = re.search(r'"title":\s*"([^"]+)"', html)
                cfg = {
                    "request": {"files": {"progressive": arr}},
                    "video": {"title": title_m.group(1) if title_m else f"Vimeo {vid}",
                            "owner": {}, "duration": None, "thumbs": {}},
                }
        except Exception:
            cfg = None
    if not cfg:
        return None
    files = (cfg.get("request") or {}).get("files") or {}
    progressive = files.get("progressive") or []
    if not progressive:
        return None
    video = cfg.get("video") or {}
    thumbs = video.get("thumbs") or {}
    thumb = thumbs.get("base") or (video.get("thumbnail") or "")
    formats = []
    for f in progressive:
        h = f.get("height")
        if not h:
            continue
        formats.append({
            "format_id": f"vimeo-{h}",
            "url": f.get("url"),
            "height": h,
            "width": f.get("width"),
            "ext": "mp4",
            "vcodec": "h264",
            "acodec": "aac",
            "filesize": f.get("size"),
        })
    if not formats:
        return None
    return {
        "title": video.get("title") or f"Vimeo {vid}",
        "uploader": (video.get("owner") or {}).get("name") or "",
        "duration": video.get("duration"),
        "thumbnail": thumb,
        "extractor_key": "Vimeo",
        "webpage_url": url,
        "formats": formats,
        "_no_audio": True,  # progressive files are combined; no separate audio
    }


def _download_vimeo_direct(url, fmt, workdir):
    """Download a Vimeo progressive MP4 directly (no yt-dlp). Picks the
    file matching the height in the format selector. Returns the saved
    path, or None if it could not be resolved."""
    info = _vimeo_fallback(url)
    if not info:
        return None
    m = re.search(r"height<=?(\d+)", fmt or "")
    want = int(m.group(1)) if m else None
    files = sorted(info["formats"], key=lambda f: f["height"], reverse=True)
    pick = None
    if want:
        at_or_below = [f for f in files if f["height"] <= want]
        pick = at_or_below[0] if at_or_below else files[-1]
    else:
        pick = files[0]
    if not pick or not pick.get("url"):
        return None
    req = urllib.request.Request(
        pick["url"],
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                 "Referer": url},
    )
    path = os.path.join(workdir, "file.mp4")
    with urllib.request.urlopen(req, timeout=300) as resp, open(path, "wb") as out:
        shutil.copyfileobj(resp, out)
    return path if os.path.getsize(path) > 0 else None


def fetch_info(url):
    """Return metadata + download options for a public video URL."""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        # YouTube: try the web player first — on a host whose IP is not
        # bot-checked it returns the full quality ladder (up to 4K).
        # Fall back to the app/TV clients (android etc.) when web is
        # blocked; they return fewer formats but still download.
        "extractor_args": {
            "youtube": {"player_client": ["web", "android", "ios", "tv_embedded"]},
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        # Vimeo's web client needs a login; try its player config directly.
        if "vimeo.com" in url:
            info = _vimeo_fallback(url)
            if info is not None:
                return info
        raise
    if info is None:
        raise ValueError("Could not fetch this link.")
    if info.get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        if not entries:
            raise ValueError("Could not fetch this link.")
        info = entries[0]
    return info


def build_options(info):
    """Curated download options: one best MP4 per height + one audio.
    When ffmpeg is available, video uses separate video+audio streams
    merged into MP4 (best quality). Without ffmpeg (Vercel), video uses
    the best combined format so no merge is needed, and audio is the
    native stream (M4A/WebM) instead of a converted MP3."""
    formats = info.get("formats") or []
    heights = sorted(
        {f.get("height") for f in formats
         if f.get("vcodec") not in (None, "none") and f.get("height")},
        reverse=True,
    )
    has_ffmpeg = _has_ffmpeg()
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
        if has_ffmpeg:
            fmt_id = f"bv*[height={h}]+ba/b[height<={h}]"
        else:
            fmt_id = f"b[height<={h}]"
        options.append({
            "id": fmt_id,
            "label": f"{h}p",
            "ext": "mp4",
            "size": size,
            "kind": "video",
        })
    # Fallback: if no height-based formats were found, offer best combined.
    if not options:
        options.append({
            "id": "bv*+ba/b" if has_ffmpeg else "b",
            "label": "Best quality",
            "ext": "mp4",
            "size": None,
            "kind": "video",
        })
    if not info.get("_no_audio"):
        if has_ffmpeg:
            options.append({
                # "bestaudio" alone fails for direct files, whose only
                # format is a combined stream — fall back to best combined.
                "id": "bestaudio/bv*+ba/b",
                "label": "MP3 audio",
                "ext": "mp3",
                "size": None,
                "kind": "audio",
            })
        else:
            # No ffmpeg to convert with: offer the native audio stream.
            audio_ext = "m4a"
            audio_only = [f for f in formats
                          if f.get("vcodec") in (None, "none")
                          and f.get("acodec") not in (None, "none")]
            if audio_only:
                audio_only.sort(key=lambda x: x.get("abr") or 0, reverse=True)
                audio_ext = (audio_only[0].get("ext") or "m4a").lower()
            options.append({
                "id": "bestaudio/bv*+ba/b",
                "label": f"Audio ({audio_ext.upper()})",
                "ext": audio_ext,
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
        # Vimeo: yt-dlp's web client needs a login — download the
        # progressive MP4 straight from the player config instead.
        if "vimeo.com" in url and kind == "video":
            direct = _download_vimeo_direct(url, fmt, workdir)
            if direct:
                return send_file(
                    direct,
                    mimetype="video/mp4",
                    as_attachment=True,
                    download_name=_clean_filename(title, "mp4"),
                    max_age=0,
                )
        # Some extractors (Snapchat) report a nonsense "extension" — a
        # random token from the URL, e.g. 'IRZXSOY' — and yt-dlp then
        # refuses to save the file ("extracted extension is unusual").
        # Force a sane extension in the output name, and remux to real
        # MP4 when ffmpeg is available so the file matches its name.
        if kind == "audio" and _has_ffmpeg():
            out_tmpl = os.path.join(workdir, "file.mp3")
        elif kind == "video":
            out_tmpl = os.path.join(workdir, "file.mp4")
        else:
            out_tmpl = os.path.join(workdir, "file.%(ext)s")
        cmd = YTDLP_CMD + [
            "-f", fmt,
            "--no-playlist",
            "--no-warnings",
            "--no-progress",
            # Some extractors (Snapchat) report a nonsense "extension"
            # (a random token from the URL, e.g. 'IRZXSOY') and yt-dlp
            # otherwise refuses to save the file. Allow it: the stream
            # is only ever written into our own throwaway temp dir and
            # the file we serve is forced to a real .mp4/.mp3 below.
            "--compat-options", "allow-unsafe-ext",
            "--extractor-args", "youtube:player_client=web,android,ios,tv_embedded",
            "-o", out_tmpl,
        ]
        ffloc = _ffmpeg_location()
        if ffloc:
            cmd += ["--ffmpeg-location", ffloc]
        # Only convert to MP3 when ffmpeg exists; otherwise the best
        # audio stream is downloaded as-is (M4A/WebM).
        if kind == "audio" and _has_ffmpeg():
            cmd += ["-x", "--audio-format", "mp3"]
        else:
            cmd += ["--merge-output-format", "mp4"]
            if kind == "video" and _has_ffmpeg():
                cmd += ["--remux-video", "mp4"]
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
        mimetype = {
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
            "webm": "audio/webm" if kind == "audio" else "video/webm",
            "opus": "audio/ogg",
            "mp4": "video/mp4",
        }.get(ext, "video/mp4")
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
