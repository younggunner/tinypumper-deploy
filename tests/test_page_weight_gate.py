"""Runs scripts/check-page-weight.py on small fake built sites: each rule fails on a page that breaks it
and passes on a page that follows it. Run: python3 -m unittest discover -s tests (page-weight gate workflow)"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/check-page-weight.py"
LOADER = '<script src="/assets/js/gb-light-media.js" defer></script>'
GOOD_VIDEO = ('<video data-light-video muted loop playsinline preload="none" poster="/p.webp">'
              '<source data-src="/assets/video/x.mp4" type="video/mp4"></video>')


class PageWeightGate(unittest.TestCase):
    def run_gate(self, html, video_bytes=1000):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            (site / "assets/video").mkdir(parents=True)
            (site / "assets/video/x.mp4").write_bytes(b"0" * video_bytes)
            (site / "page").mkdir()
            (site / "page/index.html").write_text(f"<html><body>{html}</body></html>")
            r = subprocess.run([sys.executable, str(GATE), str(site)], capture_output=True, text=True)
            return r.returncode, r.stdout

    def assertFails(self, html, why, **kw):
        code, out = self.run_gate(html, **kw)
        self.assertEqual(code, 1, out)
        self.assertIn(why, out)

    def test_a_light_page_passes(self):
        imgs = "".join(f'<img src="/i{n}.webp">' for n in range(12)) + '<img src="/late.webp" loading="lazy">'
        code, out = self.run_gate(GOOD_VIDEO + '<div data-bg="/t.webp"></div>' + imgs + LOADER)
        self.assertEqual(code, 0, out)

    def test_video_that_plays_on_open_fails(self):
        self.assertFails('<video autoplay muted loop><source src="/assets/video/x.mp4"></video>', "<video autoplay>")

    def test_looping_video_with_src_or_no_poster_fails(self):
        self.assertFails(GOOD_VIDEO.replace("data-src=", "src=") + LOADER, "has src")
        self.assertFails(GOOD_VIDEO.replace(' poster="/p.webp"', "") + LOADER, "without a poster")

    def test_overlay_clip_needs_no_poster(self):
        clip = '<video data-light-video data-overlay muted loop preload="none" data-src="/assets/video/x.mp4"></video>'
        self.assertEqual(self.run_gate(clip + LOADER)[0], 0)

    def test_remote_or_heavy_loop_fails(self):
        remote = GOOD_VIDEO.replace("/assets/video/x.mp4", "https://raw.githubusercontent.com/a/b/main/v.mp4")
        self.assertFails(remote + LOADER, "host a light copy on this site")
        self.assertFails(GOOD_VIDEO + LOADER, "over 600 KB", video_bytes=700 * 1024)

    def test_loops_or_lazy_thumbnails_without_the_loader_fail(self):
        self.assertFails(GOOD_VIDEO, "does not load the light-media loader")
        self.assertFails('<div data-bg="/t.webp"></div>', "does not load the light-media loader")

    def test_too_many_images_on_open_fails(self):
        imgs = "".join(f'<img src="/i{n}.webp">' for n in range(12))
        self.assertFails(imgs + '<div style="background-image:url(/x.webp)"></div>', "13 images load on open")

    def test_markup_in_scripts_and_noscript_is_ignored(self):
        html = ("<script>var v='<video autoplay>';</script>"
                + "<noscript>" + "".join(f'<img src="/px{n}.gif">' for n in range(20)) + "</noscript>")
        self.assertEqual(self.run_gate(html)[0], 0)

    def test_relative_video_paths_resolve_from_the_page(self):
        rel = GOOD_VIDEO.replace("/assets/video/x.mp4", "../assets/video/x.mp4")
        self.assertEqual(self.run_gate(rel + LOADER)[0], 0)
        self.assertFails(rel.replace("x.mp4", "gone.mp4") + LOADER, "is missing")

    def test_unmarked_loop_fails_but_tap_to_play_passes(self):
        self.assertFails('<video muted loop playsinline src="/assets/video/x.mp4"></video>', "without data-light-video")
        self.assertEqual(self.run_gate('<video controls preload="none" src="/big.mp4"></video>')[0], 0)

    def test_single_quoted_sources_are_checked(self):
        remote = GOOD_VIDEO.replace('data-src="/assets/video/x.mp4"', "data-src='https://cdn.example.com/v.mp4'")
        self.assertFails(remote + LOADER, "host a light copy on this site")

    def run_images(self, html):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            (site / "big.webp").write_bytes(b"0" * (260 * 1024))
            (site / "small.webp").write_bytes(b"0" * 1000)
            (site / "page").mkdir()
            (site / "page/index.html").write_text(f"<html><body>{html}</body></html>")
            r = subprocess.run([sys.executable, str(GATE), str(site)], capture_output=True, text=True)
            return r.returncode, r.stdout

    def test_heavy_images_fail_in_every_place_a_page_uses_them(self):
        for html in ('<img src="/big.webp" loading="lazy">',
                     '<video data-light-video controls poster="/big.webp"></video>' + LOADER,
                     '<div data-bg="/big.webp"></div>' + LOADER,
                     '<div style="background-image:url(/big.webp)"></div>',
                     "<style>.h{background-image:linear-gradient(#000,#111),url('/big.webp')}</style>",
                     '<style>.h{background:#000 url("../big.webp") no-repeat}</style>'):
            with self.subTest(html=html):
                code, out = self.run_images(html)
                self.assertEqual(code, 1, out)
                self.assertIn("is 260 KB, over 250 KB", out)

    def test_light_images_pass_in_every_place(self):
        html = ('<img src="../small.webp"><div data-bg="/small.webp"></div>'
                "<style>.h{background:linear-gradient(#000,#111),url('/small.webp')}</style>" + LOADER)
        code, out = self.run_images(html)
        self.assertEqual(code, 0, out)

    def test_github_hosted_images_fail(self):
        code, out = self.run_images('<img src="https://raw.githubusercontent.com/a/b/main/x.png" loading="lazy">')
        self.assertEqual(code, 1, out)
        self.assertIn("host a copy on this site", out)

    def test_heavy_html_fails(self):
        self.assertFails("<p>" + "x" * (601 * 1024) + "</p>", "over 600 KB")


if __name__ == "__main__":
    unittest.main()
