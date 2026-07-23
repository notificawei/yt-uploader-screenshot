#!/usr/bin/env python3
"""GUI app for capturing full-page screenshots of YouTube channel pages."""

import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

BG       = "#ffffff"
BORDER   = "#e0e0e0"
ACCENT   = "#ff0000"
ACCENT_H = "#cc0000"
TEXT     = "#111111"
SUBTEXT  = "#666666"
INPUT_BG = "#f5f5f5"
SUCCESS  = "#16a34a"
ERROR_C  = "#dc2626"

FONT_TITLE = ("Helvetica Neue", 17, "bold")
FONT_LABEL = ("Helvetica Neue", 11)
FONT_SMALL = ("Helvetica Neue", 10)
FONT_BTN   = ("Helvetica Neue", 13, "bold")
FONT_MONO  = ("Menlo", 10)


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
    raw = channel.strip().lstrip("@")
    # strip URL noise
    raw = re.sub(r"https?://(?:www\.)?youtube\.com/@?", "", raw)
    slug = re.sub(r"[^\w\-]", "_", raw).strip("_") or "channel"
    return str(Path.home() / "Desktop" / f"{slug}_{tab}.png")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Screenshot")
        self.geometry("540x480")
        self.minsize(540, 480)
        self.resizable(True, False)
        self.configure(bg=BG)
        self._running = False
        self._preview_img = None
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 24, "pady": 0}

        # ── Title row ─────────────────────────────────────────────────────────
        title_row = tk.Frame(self, bg=BG)
        title_row.pack(fill="x", padx=24, pady=(20, 18))
        tk.Label(title_row, text="▶", font=("Helvetica Neue", 20, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left", padx=(0, 8))
        tk.Label(title_row, text="YouTube Screenshot",
                 font=FONT_TITLE, fg=TEXT, bg=BG).pack(side="left")

        # ── URL input ─────────────────────────────────────────────────────────
        tk.Label(self, text="Channel URL or handle", font=FONT_SMALL,
                 fg=SUBTEXT, bg=BG, anchor="w").pack(fill="x", padx=24, pady=(0, 4))

        url_frame = tk.Frame(self, bg=INPUT_BG,
                             highlightthickness=1, highlightbackground=BORDER)
        url_frame.pack(fill="x", padx=24, pady=(0, 16))

        self._url_var = tk.StringVar()
        self._url_entry = tk.Entry(
            url_frame, textvariable=self._url_var,
            font=FONT_LABEL, bg=INPUT_BG, fg=SUBTEXT,
            insertbackground=TEXT, relief="flat", bd=10,
        )
        self._url_entry.pack(fill="x")
        self._url_entry.insert(0, "https://www.youtube.com/@...")
        self._url_entry.bind("<FocusIn>",  self._clear_placeholder)
        self._url_entry.bind("<FocusOut>", self._restore_placeholder)
        self._url_entry.bind("<Return>",   lambda _: self._start_capture())

        # ── Options row ───────────────────────────────────────────────────────
        opts = tk.Frame(self, bg=BG)
        opts.pack(fill="x", padx=24, pady=(0, 16))

        # Tab
        col0 = tk.Frame(opts, bg=BG)
        col0.pack(side="left", padx=(0, 24))
        tk.Label(col0, text="Tab", font=FONT_SMALL, fg=SUBTEXT, bg=BG,
                 anchor="w").pack(fill="x")
        self._tab_var = tk.StringVar(value="videos")
        tab_cb = ttk.Combobox(col0, textvariable=self._tab_var, width=12,
                              values=["home","videos","shorts","live",
                                      "playlists","community","about"],
                              state="readonly", font=FONT_LABEL)
        tab_cb.pack()

        # Width
        col1 = tk.Frame(opts, bg=BG)
        col1.pack(side="left", padx=(0, 24))
        tk.Label(col1, text="Viewport width (px)", font=FONT_SMALL,
                 fg=SUBTEXT, bg=BG, anchor="w").pack(fill="x")
        self._width_var = tk.StringVar(value="1400")
        tk.Entry(col1, textvariable=self._width_var, width=7,
                 font=FONT_LABEL, bg=INPUT_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 bd=6).pack()

        # Full page
        col2 = tk.Frame(opts, bg=BG)
        col2.pack(side="left", pady=(16, 0))
        self._fullpage_var = tk.BooleanVar(value=True)
        tk.Checkbutton(col2, text="Full page",
                       variable=self._fullpage_var,
                       font=FONT_SMALL, fg=TEXT, bg=BG,
                       activebackground=BG, activeforeground=TEXT,
                       selectcolor=INPUT_BG).pack()

        # ── Save path ─────────────────────────────────────────────────────────
        tk.Label(self, text="Save to", font=FONT_SMALL,
                 fg=SUBTEXT, bg=BG, anchor="w").pack(fill="x", padx=24, pady=(0, 4))

        save_row = tk.Frame(self, bg=BG)
        save_row.pack(fill="x", padx=24, pady=(0, 20))

        self._output_var = tk.StringVar()
        tk.Entry(save_row, textvariable=self._output_var,
                 font=FONT_MONO, bg=INPUT_BG, fg=SUBTEXT,
                 insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 bd=6).pack(side="left", fill="x", expand=True)

        tk.Button(save_row, text="Browse…", font=FONT_SMALL,
                  bg=INPUT_BG, fg=TEXT, activebackground=BORDER,
                  relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2",
                  command=self._browse).pack(side="left", padx=(6, 0))

        self._update_output()
        self._url_var.trace_add("write", lambda *_: self._update_output())
        self._tab_var.trace_add("write", lambda *_: self._update_output())

        # ── Capture button ────────────────────────────────────────────────────
        self._capture_btn = tk.Button(
            self, text="  Capture Screenshot  ",
            font=FONT_BTN,
            bg=ACCENT, fg="white",
            activebackground=ACCENT_H, activeforeground="white",
            relief="flat", bd=0, pady=12,
            cursor="hand2",
            command=self._start_capture,
        )
        self._capture_btn.pack(fill="x", padx=24, pady=(0, 10))

        # ── Progress + status ─────────────────────────────────────────────────
        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._progress.pack(fill="x", padx=24, pady=(0, 6))

        self._status_var = tk.StringVar(value="")
        self._status_lbl = tk.Label(self, textvariable=self._status_var,
                                    font=FONT_SMALL, fg=SUBTEXT, bg=BG,
                                    anchor="w", wraplength=490)
        self._status_lbl.pack(fill="x", padx=24)

        # ── Open button (hidden until success) ────────────────────────────────
        self._open_btn = tk.Button(
            self, text="Open Screenshot",
            font=FONT_SMALL,
            bg=INPUT_BG, fg=TEXT,
            activebackground=BORDER,
            relief="flat", bd=0, padx=14, pady=7,
            cursor="hand2",
            command=self._open_file,
        )

        # ── Preview (hidden until success) ────────────────────────────────────
        self._preview_lbl = tk.Label(self, bg=BG)

        # ttk style
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TProgressbar", troughcolor=INPUT_BG, background=ACCENT)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _clear_placeholder(self, _):
        if self._url_var.get() == "https://www.youtube.com/@...":
            self._url_entry.delete(0, "end")
            self._url_entry.configure(fg=TEXT)

    def _restore_placeholder(self, _):
        if not self._url_var.get().strip():
            self._url_entry.insert(0, "https://www.youtube.com/@...")
            self._url_entry.configure(fg=SUBTEXT)

    def _update_output(self):
        ch = self._url_var.get().strip()
        if ch and ch != "https://www.youtube.com/@...":
            self._output_var.set(default_output(ch, self._tab_var.get()))

    def _browse(self):
        current = self._output_var.get()
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
            initialfile=Path(current).name if current else "screenshot.png",
        )
        if path:
            self._output_var.set(path)

    def _set_status(self, msg, color=SUBTEXT):
        self._status_var.set(msg)
        self._status_lbl.configure(fg=color)

    def _open_file(self):
        path = self._output_var.get()
        if path and Path(path).exists():
            subprocess.run(["open", path])

    # ── Capture ───────────────────────────────────────────────────────────────
    def _start_capture(self):
        if self._running:
            return
        channel = self._url_var.get().strip()
        if not channel or channel == "https://www.youtube.com/@...":
            messagebox.showwarning("No URL", "Please enter a YouTube channel URL or @handle.")
            return
        try:
            width = int(self._width_var.get())
        except ValueError:
            messagebox.showerror("Invalid width", "Viewport width must be a whole number.")
            return
        output = self._output_var.get().strip()
        if not output:
            messagebox.showerror("No output path", "Please choose where to save the file.")
            return

        self._running = True
        self._capture_btn.configure(state="disabled", text="  Capturing…  ")
        self._open_btn.pack_forget()
        self._preview_lbl.configure(image="")
        self._preview_lbl.pack_forget()
        self._progress.start(12)
        self._set_status("Starting browser…")

        threading.Thread(
            target=self._run_capture,
            args=(channel, self._tab_var.get(), width,
                  self._fullpage_var.get(), output),
            daemon=True,
        ).start()

    def _run_capture(self, channel, tab, width, full_page, output):
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWT

            url = build_url(channel, tab)
            self.after(0, self._set_status, f"Opening {url} …")

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
                    self.after(0, self._set_status, "Scrolling to load all content…")
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

                self.after(0, self._set_status, "Taking screenshot…")
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=output, full_page=full_page)
                browser.close()

            self.after(0, self._on_success, output)
        except Exception as exc:
            self.after(0, self._on_error, str(exc))

    def _on_success(self, output):
        self._running = False
        self._progress.stop()
        self._capture_btn.configure(state="normal", text="  Capture Screenshot  ")
        size_kb = Path(output).stat().st_size // 1024
        self._set_status(f"Saved: {output}  ({size_kb} KB)", SUCCESS)
        self._open_btn.pack(padx=24, pady=(8, 0), anchor="w")
        self._show_preview(output)

    def _on_error(self, msg):
        self._running = False
        self._progress.stop()
        self._capture_btn.configure(state="normal", text="  Capture Screenshot  ")
        self._set_status(f"Error: {msg}", ERROR_C)
        messagebox.showerror("Capture failed", msg)

    def _show_preview(self, path):
        if not PIL_AVAILABLE:
            return
        try:
            img = Image.open(path)
            max_w = self.winfo_width() - 48
            ratio = max_w / img.width
            new_h = int(img.height * ratio)
            thumb = img.resize((max_w, min(new_h, 360)), Image.LANCZOS)
            self._preview_img = ImageTk.PhotoImage(thumb)
            self._preview_lbl.configure(image=self._preview_img)
            self._preview_lbl.pack(padx=24, pady=(10, 16))
        except Exception:
            pass


if __name__ == "__main__":
    app = App()
    app.mainloop()
