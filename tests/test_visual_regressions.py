"""Browser-level regression coverage for objective visual contracts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Error, Page, sync_playwright


STYLE_PATH = Path(__file__).parents[1] / "src" / "loremaster" / "web" / "style.css"


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(headless=True)
        except Error as exc:
            if "Executable doesn't exist" in str(exc):
                raise RuntimeError(
                    "Chromium is required for visual regressions; run "
                    "`uv run playwright install chromium`"
                ) from exc
            raise
        yield instance
        instance.close()


def _page_with_styles(browser: Browser, body: str) -> Page:
    page = browser.new_page(viewport={"width": 288, "height": 720})
    stylesheet = STYLE_PATH.read_text(encoding="utf-8")
    page.set_content(f"<style>{stylesheet}</style>{body}")
    return page


def test_campaign_picker_respects_hidden_and_mobile_width(browser: Browser):
    page = _page_with_styles(
        browser,
        """
        <main>
          <div id="picker-slot" style="width: 180px">
            <label id="picker" class="campaign-picker" hidden>
              Campanha
              <select><option>Return of the Setting Sun</option></select>
            </label>
          </div>
        </main>
        """,
    )
    picker = page.locator("#picker")

    assert picker.evaluate("element => getComputedStyle(element).display") == "none"

    picker.evaluate("element => element.removeAttribute('hidden')")
    assert picker.evaluate("element => getComputedStyle(element).display") == "grid"
    assert page.evaluate(
        """document.querySelector('#picker select').getBoundingClientRect().right
            <= document.querySelector('#picker-slot').getBoundingClientRect().right"""
    )
    assert page.evaluate(
        "document.documentElement.scrollWidth === document.documentElement.clientWidth"
    )
    page.close()


def test_reconstruction_controls_keep_dark_theme_and_dimensions(browser: Browser):
    page = _page_with_styles(
        browser,
        """
        <main>
          <div class="class-level-row">
            <label>Classe<select id="class-select"><option>Guerreiro</option></select></label>
            <label>Nível<input id="class-level" type="number" value="5"></label>
            <label class="class-starting">
              <input id="class-starting" type="radio" checked>Classe inicial
            </label>
          </div>
          <div class="import-stat-grid">
            <label>Força<input id="import-strength" type="number" value="15"></label>
          </div>
          <div class="import-hp-grid">
            <label>HP máximo<input id="maximum-hp" type="number" value="52"></label>
          </div>
        </main>
        """,
    )

    expected = {
        "background": "rgb(13, 17, 23)",
        "border": "rgb(48, 54, 61)",
        "color": "rgb(230, 237, 243)",
        "colorScheme": "dark",
        "minHeight": "42px",
    }
    for selector in ("#class-select", "#class-level", "#import-strength", "#maximum-hp"):
        styles = page.locator(selector).evaluate(
            """element => {
                const style = getComputedStyle(element);
                return {
                    background: style.backgroundColor,
                    border: style.borderTopColor,
                    color: style.color,
                    colorScheme: style.colorScheme,
                    minHeight: style.minHeight,
                };
            }"""
        )
        assert styles == expected

    radio = page.locator("#class-starting")
    radio_styles = radio.evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                accentColor: style.accentColor,
                height: style.height,
                width: style.width,
            };
        }"""
    )
    assert radio_styles == {
        "accentColor": "rgb(88, 166, 255)",
        "height": "18px",
        "width": "18px",
    }
    assert page.evaluate(
        "document.documentElement.scrollWidth === document.documentElement.clientWidth"
    )
    page.close()
