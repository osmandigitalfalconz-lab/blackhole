# BlackHole — free online video downloader

Paste a public video link (YouTube, Facebook, Instagram, X, Pinterest,
Threads, Reddit, Dailymotion, Snapchat, RedNote, …) and download it as MP4
(up to 4K where available) or MP3. No signup, no watermark, no app needed.

A working clone of [GreenHole](https://greenhole.app/), rebuilt under the
BlackHole name with a dark theme. Videos are fetched on demand with
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and streamed to the user — nothing
is stored on the server.

## What is inside

| File | What it does |
| --- | --- |
| `server.py` | Flask backend: `POST /api/info` (video metadata + quality options), `GET /api/download` (streams the MP4/MP3), plus basic rate limiting and SSRF protection |
| `static/index.html` | Downloader page: hero, link box, multiple-links mode, platform pills, how it works, FAQ |
| `static/app.js` | Frontend logic (fetch info, render quality buttons, start downloads) |
| `static/style.css` | Dark “black hole” theme |
| `static/how-to.html`, `terms.html`, `privacy.html`, `disclaimer.html` | Content pages |
| `requirements.txt` | Flask, yt-dlp, gunicorn |
| `Dockerfile` | Container image (Python + ffmpeg) |

## Run it locally

```bash
pip install -r requirements.txt
python server.py        # http://127.0.0.1:5000
```

Or with Docker:

```bash
docker build -t blackhole .
docker run -p 5000:5000 blackhole
```

## Deploy it

This is a real backend, not a static site — it will **not** work on Vercel
or plain static hosting. It needs a host that runs Python + ffmpeg:

- **Render / Railway / Fly.io** — connect this repo, set the start command to
  `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 600 server:app`
- **A small VPS** — `pip install -r requirements.txt`, install ffmpeg
  (`apt install ffmpeg`), then run gunicorn behind nginx or Caddy.

Notes for production: keep yt-dlp up to date (`pip install -U yt-dlp`) —
platforms change their pages often and an old yt-dlp is the most common
reason a fetch fails. YouTube may rate-limit datacentre IPs; a residential
or low-traffic host works better.

## Legal note

BlackHole does not host videos. Only download content you have the right to
download, for personal use, and respect copyright and the source platforms’
terms. See `static/disclaimer.html`.
