"""Pages tinypumper.com advertises to search engines and AI crawlers (sitemap.xml, llms.txt) must exist and allow
indexing; headline-test articles carry a canonical; the partner page stays direct-link only; the homepage video
controls are real named buttons. Run: python3 -m unittest discover -s tests"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page(url):
    path = re.sub(r"^https://www\.tinypumper\.com/", "", url)
    return ROOT / path / "index.html" if path else ROOT / "index.html"


class IndexablePages(unittest.TestCase):
    def test_sitemap_pages_exist_and_allow_indexing(self):
        urls = re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text())
        self.assertGreaterEqual(len(urls), 7)
        for url in urls:
            with self.subTest(url=url):
                html = page(url).read_text()
                self.assertNotRegex(html, r'name="robots"[^>]*noindex')

    def test_llms_txt_links_on_this_site_exist(self):
        for url in re.findall(r"https://www\.tinypumper\.com/[^\s)]*", (ROOT / "llms.txt").read_text()):
            if url.endswith(".txt") or url.endswith(".xml"):
                continue
            with self.subTest(url=url):
                self.assertTrue(page(url.split("#")[0]).is_file())

    def test_reads_have_canonical_without_query(self):
        for slug in ("scada-albatross", "silent-bleed", "windshield-time"):
            html = (ROOT / "reads" / slug / "index.html").read_text()
            self.assertIn(f'<link rel="canonical" href="https://www.tinypumper.com/reads/{slug}/">', html)

    def test_partner_page_stays_direct_link_only(self):
        html = (ROOT / "partner-program" / "index.html").read_text()
        self.assertRegex(html, r'name="robots" content="noindex')
        self.assertNotIn("partner-program", (ROOT / "sitemap.xml").read_text())

    def test_robots_names_meta_webindexer(self):
        self.assertRegex((ROOT / "robots.txt").read_text(), r"User-agent: meta-webindexer\s+Allow: /")

    def test_homepage_video_controls_are_named_buttons(self):
        html = (ROOT / "index.html").read_text()
        # a modal's backdrop may close on click (the modal has its own close control); any other
        # clickable div is a control agents cannot see
        clickable = [d for d in re.findall(r"<div[^>]*onclick=[^>]*>", html) if 'video-modal' not in d]
        self.assertEqual(clickable, [])
        self.assertNotRegex(html, r"<p[^>]*onclick=")
        buttons = re.findall(r"<button[^>]*>", html)
        video = [b for b in buttons if "Play video" in b]
        self.assertGreaterEqual(len(video), 5)
        # the overview frame is swapped into the player box, never into the button itself
        self.assertIn('id="yt-player"', html)
        self.assertRegex(html, r'<div id="yt-player"[^>]*><button type="button" aria-label="Play video: TinyPumper Overview"[^>]*onclick="this\.parentNode\.innerHTML=')


if __name__ == "__main__":
    unittest.main()
