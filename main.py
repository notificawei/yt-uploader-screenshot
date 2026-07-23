#!/usr/bin/env python3
"""Capture a full-page screenshot of a YouTube uploader/channel page."""

import re
import sys
import time
from pathlib import Path

import click
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def normalize_url(channel: str) -> str:
    """Accept a channel URL, handle (@name), or channel ID and return a full URL."""
    channel = channel.strip()
    if channel.startswith("http://") or channel.startswith("https://"):
        return channel
    if channel.startswith("@"):
        return f"https://www.youtube.com/{channel}"
    if re.match(r"^UC[A-Za-z0-9_-]{22}$", channel):
        return f"https://www.youtube.com/channel/{channel}"
    return f"https://www.youtube.com/@{channel}"


def scroll_to_bottom(page, pause: float = 1.5, max_scrolls: int = 30):
    """Scroll down incrementally so lazy-loaded content renders."""
    prev_height = 0
    for _ in range(max_scrolls):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(pause)
        height = page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)


@click.command()
@click.argument("channel")
@click.option(
    "--output", "-o",
    default=None,
    help="Output file path (default: <channel_handle>.png in current directory)",
)
@click.option(
    "--width", "-w",
    default=1400,
    show_default=True,
    help="Viewport width in pixels",
)
@click.option(
    "--tab",
    default="videos",
    type=click.Choice(["home", "videos", "shorts", "live", "playlists", "community", "about"]),
    show_default=True,
    help="Which channel tab to capture",
)
@click.option(
    "--full-page/--no-full-page",
    default=True,
    show_default=True,
    help="Capture the entire scrollable page",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    show_default=True,
    help="Run browser in headless mode",
)
@click.option(
    "--scroll/--no-scroll",
    default=True,
    show_default=True,
    help="Scroll to bottom first so lazy content loads (recommended for full-page)",
)
def capture(channel, output, width, tab, full_page, headless, scroll):
    """Capture a full-page screenshot of a YouTube CHANNEL uploader page.

    CHANNEL can be a handle (@MrBeast), a channel ID (UCxxxxxxx),
    or a full YouTube URL.

    Examples:

    \b
      python main.py @MrBeast
      python main.py MrBeast --tab videos --output mrbeast.png
      python main.py https://www.youtube.com/@veritasium
    """
    base_url = normalize_url(channel)
    if tab and tab != "home":
        url = f"{base_url.rstrip('/')}/{tab}"
    else:
        url = base_url

    # Derive default output filename
    if output is None:
        slug = re.sub(r"[^\w\-]", "_", channel.lstrip("@").lstrip("https://www.youtube.com/").strip("/"))
        output = f"{slug}_{tab}.png"

    output_path = Path(output)

    click.echo(f"  URL    : {url}")
    click.echo(f"  Output : {output_path.resolve()}")
    click.echo(f"  Width  : {width}px  |  full-page: {full_page}  |  headless: {headless}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": width, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()

        click.echo("  Navigating…")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeout:
            click.echo("  Warning: page load timed out, attempting screenshot anyway…", err=True)

        # Dismiss cookie/consent dialogs if present
        for selector in [
            'button[aria-label="Accept all"]',
            'button:has-text("Accept all")',
            'button:has-text("I agree")',
            'tp-yt-paper-button[aria-label="Accept all"]',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2_000):
                    btn.click()
                    time.sleep(0.8)
                    break
            except Exception:
                pass

        # Wait for main channel content
        try:
            page.wait_for_selector("ytd-channel-renderer, ytd-browse, #channel-header", timeout=10_000)
        except PlaywrightTimeout:
            pass

        time.sleep(2)

        if scroll and full_page:
            click.echo("  Scrolling to load lazy content…")
            scroll_to_bottom(page)

        click.echo("  Taking screenshot…")
        page.screenshot(path=str(output_path), full_page=full_page)
        browser.close()

    size_kb = output_path.stat().st_size // 1024
    click.echo(f"  Saved  : {output_path.resolve()}  ({size_kb} KB)")


if __name__ == "__main__":
    capture()
