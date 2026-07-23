#!/usr/bin/env python3
"""Local web UI for capturing full-page screenshots of YouTube channel pages."""

import base64
import json
import os
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Screenshot</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f2f2f7;
    min-height: 100vh;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 16px 60px;
  }
  .card {
    background: #fff;
    border-radius: 18px;
    box-shadow: 0 4px 24px rgba(0,0,0,.10);
    padding: 36px 40px 40px;
    width: 100%;
    max-width: 560px;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 28px;
  }
  .yt-icon {
    width: 36px; height: 36px;
    background: #ff0000;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }
  .yt-icon svg { width: 20px; height: 20px; fill: #fff; }
  h1 { font-size: 20px; font-weight: 700; color: #111; }

  label { display: block; font-size: 12px; font-weight: 600;
          color: #888; text-transform: uppercase; letter-spacing: .04em;
          margin-bottom: 6px; margin-top: 20px; }
  input[type=text], input[type=number], select {
    width: 100%;
    padding: 11px 14px;
    border: 1.5px solid #e0e0e0;
    border-radius: 10px;
    font-size: 15px;
    color: #111;
    background: #fafafa;
    outline: none;
    transition: border-color .15s;
  }
  input[type=text]:focus, input[type=number]:focus, select:focus {
    border-color: #ff0000;
    background: #fff;
  }
  .row { display: flex; gap: 14px; }
  .row > div { flex: 1; }

  .checkbox-row {
    display: flex; align-items: center; gap: 10px;
    margin-top: 20px;
  }
  .checkbox-row input[type=checkbox] { width: 18px; height: 18px; accent-color: #ff0000; cursor: pointer; }
  .checkbox-row span { font-size: 14px; color: #333; }

  .btn {
    display: block; width: 100%; margin-top: 28px;
    padding: 15px;
    background: #ff0000;
    color: #fff;
    font-size: 16px; font-weight: 700;
    border: none; border-radius: 12px;
    cursor: pointer;
    transition: background .15s, transform .1s;
  }
  .btn:hover { background: #cc0000; }
  .btn:active { transform: scale(.98); }
  .btn:disabled { background: #ccc; cursor: default; }

  #status-box {
    display: none;
    margin-top: 22px;
    padding: 14px 16px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
  }
  .status-running { background: #fff7ed; color: #92400e; border: 1.5px solid #fcd34d; }
  .status-ok      { background: #f0fdf4; color: #166534; border: 1.5px solid #86efac; }
  .status-err     { background: #fef2f2; color: #991b1b; border: 1.5px solid #fca5a5; }

  progress {
    display: none; width: 100%; height: 6px;
    margin-top: 10px; border-radius: 99px;
    accent-color: #ff0000;
  }

  #preview-box { display: none; margin-top: 22px; text-align: center; }
  #preview-box img {
    max-width: 100%; border-radius: 10px;
    box-shadow: 0 2px 12px rgba(0,0,0,.12);
  }
  .open-btn {
    display: inline-block; margin-top: 14px;
    padding: 10px 24px;
    background: #f2f2f7; color: #111;
    font-size: 14px; font-weight: 600;
    border-radius: 10px; text-decoration: none;
    border: 1.5px solid #ddd;
  }
  .open-btn:hover { background: #e5e5ea; }
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="yt-icon">
      <svg viewBox="0 0 24 24"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8zM9.7 15.5V8.5l6.3 3.5-6.3 3.5z"/></svg>
    </div>
    <h1>YouTube Screenshot</h1>
  </div>

  <form id="form">
    <label for="url">Channel URL or handle</label>
    <input type="text" id="url" name="url" placeholder="https://www.youtube.com/@MrBeast" autocomplete="off" required>

    <div class="row">
      <div>
        <label for="tab">Tab</label>
        <select id="tab" name="tab">
          <option value="videos" selected>Videos</option>
          <option value="home">Home</option>
          <option value="shorts">Shorts</option>
          <option value="live">Live</option>
          <option value="playlists">Playlists</option>
          <option value="community">Community</option>
          <option value="about">About</option>
        </select>
      </div>
      <div>
        <label for="width">Viewport width (px)</label>
        <input type="number" id="width" name="width" value="1400" min="320" max="3840">
      </div>
    </div>

    <div class="checkbox-row">
      <input type="checkbox" id="fullpage" name="fullpage" checked>
      <span>Capture full page (scroll to load all content)</span>
    </div>

    <button class="btn" type="submit" id="btn">Capture Screenshot</button>
  </form>

  <div id="status-box"></div>
  <progress id="prog"></progress>
  <div id="preview-box">
    <img id="preview-img" src="" alt="Screenshot preview">
    <br>
    <a class="open-btn" id="open-link" href="#" target="_blank">Open Full Screenshot</a>
  </div>
</div>

<script>
const form     = document.getElementById('form');
const btn      = document.getElementById('btn');
const statusBox= document.getElementById('status-box');
const prog     = document.getElementById('prog');
const previewBox= document.getElementById('preview-box');
const previewImg= document.getElementById('preview-img');
const openLink = document.getElementById('open-link');

function setStatus(msg, type) {
  statusBox.textContent = msg;
  statusBox.className = 'status-' + type;
  statusBox.style.display = 'block';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  btn.disabled = true;
  btn.textContent = 'Capturing…';
  previewBox.style.display = 'none';
  prog.style.display = 'block';
  setStatus('Starting browser…', 'running');

  const params = new URLSearchParams({
    url:      document.getElementById('url').value,
    tab:      document.getElementById('tab').value,
    width:    document.getElementById('width').value,
    fullpage: document.getElementById('fullpage').checked ? '1' : '0',
  });

  try {
    const res  = await fetch('/capture?' + params);
    const data = await res.json();
    prog.style.display = 'none';

    if (data.ok) {
      setStatus('Saved: ' + data.path + '  (' + data.size_kb + ' KB)', 'ok');
      if (data.preview) {
        previewImg.src = 'data:image/png;base64,' + data.preview;
        openLink.href  = '/file?path=' + encodeURIComponent(data.path);
        previewBox.style.display = 'block';
      }
    } else {
      setStatus('Error: ' + data.error, 'err');
    }
  } catch (err) {
    prog.style.display = 'none';
    setStatus('Request failed: ' + err, 'err');
  }

  btn.disabled = false;
  btn.textContent = 'Capture Screenshot';
});
</script>
</body>
</html>
"""


def normalize_url(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("http://") or channel.startswith("https://"):
        return channel
    if channel.startswith("@"):
        return f"https://www.youtube.com/{channel}"
    if re.match(r"^UC[A-Za-z0-9_-]{22}$", channel):
        return f"https://www.youtube.com/channel/{channel}"
    return f"https://www.youtube.com/@{channel}"


def build_url(channel: str, tab: str) -> str:
    base = normalize_url(channel)
    if tab and tab != "home":
        return f"{base.rstrip('/')}/{tab}"
    return base


def default_output(channel: str, tab: str) -> str:
    raw = re.sub(r"https?://(?:www\.)?youtube\.com/@?", "", channel.strip().lstrip("@"))
    slug = re.sub(r"[^\w\-]", "_", raw).strip("_") or "channel"
    return str(Path.home() / "Desktop" / f"{slug}_{tab}.png")


def do_capture(channel: str, tab: str, width: int, full_page: bool) -> dict:
    try:
        import time
        from playwright.sync_api import sync_playwright, TimeoutError as PWT

        url    = build_url(channel, tab)
        output = default_output(channel, tab)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": width, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except PWT:
                pass

            for sel in ['button[aria-label="Accept all"]',
                        'button:has-text("Accept all")',
                        'button:has-text("I agree")']:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2_000):
                        btn.click()
                        time.sleep(0.8)
                        break
                except Exception:
                    pass

            try:
                page.wait_for_selector(
                    "ytd-channel-renderer, ytd-browse, #channel-header",
                    timeout=10_000)
            except PWT:
                pass

            time.sleep(2)

            if full_page:
                prev_h = 0
                for _ in range(30):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    time.sleep(1.2)
                    h = page.evaluate("document.body.scrollHeight")
                    if h == prev_h:
                        break
                    prev_h = h
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(0.5)

            Path(output).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=output, full_page=full_page)
            browser.close()

        size_kb = Path(output).stat().st_size // 1024

        # Build a small thumbnail for the inline preview
        preview_b64 = None
        try:
            from PIL import Image
            import io
            img   = Image.open(output)
            ratio = 480 / img.width
            thumb = img.resize((480, min(int(img.height * ratio), 360)), Image.LANCZOS)
            buf   = io.BytesIO()
            thumb.save(buf, format="PNG")
            preview_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass

        return {"ok": True, "path": output, "size_kb": size_kb, "preview": preview_b64}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # silence request logs

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode())

        elif parsed.path == "/capture":
            qs       = parse_qs(parsed.query)
            channel  = qs.get("url",  [""])[0].strip()
            tab      = qs.get("tab",  ["videos"])[0]
            width    = int(qs.get("width", ["1400"])[0])
            full_page= qs.get("fullpage", ["1"])[0] == "1"

            if not channel:
                result = {"ok": False, "error": "No URL provided"}
            else:
                result = do_capture(channel, tab, width, full_page)

            body = json.dumps(result).encode()
            self._send(200, "application/json", body)

        elif parsed.path == "/file":
            qs   = parse_qs(parsed.query)
            path = qs.get("path", [""])[0]
            try:
                data = Path(path).read_bytes()
                self._send(200, "image/png", data)
            except Exception as e:
                self._send(404, "text/plain", str(e).encode())

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url    = f"http://localhost:{PORT}"
    print(f"Opening {url} — close this window to stop the server.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
