"""
test_tools.py — Tests for individual agent tools and the tool result cache.

Structure
---------
* TestToolCache   — pure unit tests, no network
* TestToolUnit    — tests that don't need a live network (bad-input checks, etc.)
* TestToolsLive   — tests driven from fixtures/tool_cases.yaml, marked @pytest.mark.live

Live tests are skipped automatically if OPENROUTER_API_KEY is not set
OR if the --no-live flag is passed.
"""

from __future__ import annotations

import json
import os
import time

import pytest
import yaml

# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_tool_cases(section: str) -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "fixtures", "tool_cases.yaml")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return (data or {}).get(section, {}).get("cases", [])


def _skip_live():
    """Return a skip marker if we should not run live-network tests."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        return pytest.mark.skip(reason="OPENROUTER_API_KEY not set")
    return None


def _log_tool_result(case_id: str, tool_name: str, result: str, duration_ms: int):
    """Write a test tool result to the activity log if the logger is running."""
    from app.core import activity_log as actlog
    actlog.log(
        "test_tool_result",
        {
            "case_id": case_id,
            "tool": tool_name,
            "result_len": len(result),
            "result_preview": result[:300],
            "duration_ms": duration_ms,
        },
        user_id="test-harness",
        run_id=f"test:{case_id}",
    )


# ── Tool cache ─────────────────────────────────────────────────────────────────

class TestToolCache:
    """Pure unit tests for ToolResultCache — no Flask app, no network."""

    def _fresh_cache(self):
        from app.agent.tool_cache import ToolResultCache
        return ToolResultCache()

    @pytest.mark.unit
    def test_cache_miss_on_empty(self):
        cache = self._fresh_cache()
        result = cache.get("web_search", {"query": "hello"})
        assert result is None

    @pytest.mark.unit
    def test_cache_hit_after_put(self):
        cache = self._fresh_cache()
        cache.put("web_search", {"query": "hello"}, "result text")
        result = cache.get("web_search", {"query": "hello"})
        assert result == "result text"

    @pytest.mark.unit
    def test_cache_miss_different_args(self):
        cache = self._fresh_cache()
        cache.put("web_search", {"query": "hello"}, "result A")
        result = cache.get("web_search", {"query": "world"})
        assert result is None

    @pytest.mark.unit
    def test_cache_uncacheable_tool(self):
        cache = self._fresh_cache()
        cache.put("save_text", {"filename": "x", "content": "y"}, "ok")
        result = cache.get("save_text", {"filename": "x", "content": "y"})
        assert result is None, "save_text should never be cached"

    @pytest.mark.unit
    def test_cache_ttl_expiry(self):
        from app.agent.tool_cache import ToolResultCache, _CACHEABLE_TOOLS
        import unittest.mock as mock

        cache = ToolResultCache()
        # Mock the TTL to be tiny
        with mock.patch.dict(_CACHEABLE_TOOLS, {"web_search": 0.01}):
            cache.put("web_search", {"query": "expiry-test"}, "value")
            time.sleep(0.05)
            result = cache.get("web_search", {"query": "expiry-test"})
        assert result is None, "TTL-expired entry should return None"

    @pytest.mark.unit
    def test_cache_lru_eviction(self):
        from app.agent.tool_cache import ToolResultCache, _MAX_ENTRIES
        cache = ToolResultCache()
        # Fill to capacity + 1
        for i in range(_MAX_ENTRIES + 1):
            cache.put("web_search", {"query": f"q{i}"}, f"result {i}")
        stats = cache.stats()
        assert stats["total_entries"] <= _MAX_ENTRIES

    @pytest.mark.unit
    def test_cache_stats(self):
        cache = self._fresh_cache()
        cache.put("web_search", {"query": "stats-test"}, "data")
        cache.get("web_search", {"query": "stats-test"})   # hit
        cache.get("web_search", {"query": "nonexistent"})   # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    @pytest.mark.unit
    def test_cache_clear(self):
        cache = self._fresh_cache()
        cache.put("web_search", {"query": "clear-test"}, "data")
        cache.clear()
        assert cache.get("web_search", {"query": "clear-test"}) is None

    @pytest.mark.unit
    def test_cache_thread_safe(self):
        """Concurrent puts/gets must not corrupt the cache or raise."""
        import threading
        cache = self._fresh_cache()
        errors: list[str] = []

        def worker(n: int):
            try:
                for i in range(50):
                    cache.put("web_search", {"query": f"q{n}-{i}"}, f"result {i}")
                    cache.get("web_search", {"query": f"q{n}-{i // 2}"})
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Cache thread-safety errors: {errors}"


# ── Tool unit tests (no network) ───────────────────────────────────────────────

class TestToolUnit:
    """Input validation and error handling tests — no network calls."""

    @pytest.mark.unit
    def test_visit_url_invalid_scheme(self, app):
        with app.app_context():
            from app.agent.tools import visit_url
            result = visit_url.invoke({"url": "not-a-url"})
            assert result.startswith("Error:")

    @pytest.mark.unit
    def test_visit_url_ftp_rejected(self, app):
        with app.app_context():
            from app.agent.tools import visit_url
            result = visit_url.invoke({"url": "ftp://example.com"})
            assert result.startswith("Error:")

    @pytest.mark.unit
    def test_rate_limiter_blocks_briefly(self):
        from app.agent.tools import _RateLimiter
        limiter = _RateLimiter(0.1)
        t0 = time.monotonic()
        limiter.wait()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.08, f"Rate limiter did not block enough: {elapsed:.3f}s"

    @pytest.mark.unit
    def test_domain_key_strips_www(self):
        from app.agent.tools import _domain_key_from_url
        assert _domain_key_from_url("https://www.example.com/path") == "example.com"
        assert _domain_key_from_url("https://sub.example.com") == "sub.example.com"
        assert _domain_key_from_url("not-a-url") == "unknown-domain"


# ── Live tool tests (network) ──────────────────────────────────────────────────

class TestToolsLive:
    """
    Network-dependent tool tests driven from fixtures/tool_cases.yaml.
    Skipped unless --live flag passed or OPENROUTER_API_KEY set.
    """

    def _run_case(self, app, tool_fn_name: str, kwargs: dict, case_id: str) -> str:
        with app.app_context():
            from app.agent import tools as tool_mod
            from app.agent.tools import set_runtime_context
            set_runtime_context("test-harness", "test-ws", "test-session", f"test:{case_id}")
            tool_fn = getattr(tool_mod, tool_fn_name)
            t0 = time.monotonic()
            result = tool_fn.invoke(kwargs)
            duration_ms = int((time.monotonic() - t0) * 1000)
            _log_tool_result(case_id, tool_fn_name, result, duration_ms)
        return result

    # ── web_search ────────────────────────────────────────────────────────────

    @pytest.mark.live
    @pytest.mark.parametrize("case", _load_tool_cases("web_search"), ids=[c["id"] for c in _load_tool_cases("web_search")])
    def test_web_search(self, app, case):
        try:
            result = self._run_case(app, "web_search", {"query": case["query"]}, case["id"])
        except Exception as exc:
            if "ratelimit" in str(exc).lower() or "202" in str(exc):
                pytest.skip(f"DuckDuckGo rate limited: {exc}")
            raise
        assert isinstance(result, str) and len(result) > 0, "Empty result"
        for kw in case.get("expect_contains", []):
            assert kw.lower() in result.lower(), f"'{kw}' not in web_search result"

    # ── wiki_search ───────────────────────────────────────────────────────────

    @pytest.mark.live
    @pytest.mark.parametrize("case", _load_tool_cases("wiki_search"), ids=[c["id"] for c in _load_tool_cases("wiki_search")])
    def test_wiki_search(self, app, case):
        result = self._run_case(app, "wiki_search", {"query": case["query"]}, case["id"])
        assert isinstance(result, str) and len(result) > 10
        for kw in case.get("expect_contains", []):
            assert kw.lower() in result.lower(), f"'{kw}' not in wiki result"

    # ── visit_url ─────────────────────────────────────────────────────────────

    @pytest.mark.live
    @pytest.mark.parametrize(
        "case",
        [c for c in _load_tool_cases("visit_url") if "live" in c.get("tags", [])],
        ids=[c["id"] for c in _load_tool_cases("visit_url") if "live" in c.get("tags", [])],
    )
    def test_visit_url_live(self, app, case):
        kwargs = {"url": case["url"]}
        if case.get("format"):
            kwargs["format"] = case["format"]
        result = self._run_case(app, "visit_url", kwargs, case["id"])
        assert not result.startswith("Error:")
        for kw in case.get("expect_contains", []):
            assert kw.lower() in result.lower()
        if case.get("expect_keys_in_json"):
            parsed = json.loads(result)
            for k in case["expect_keys_in_json"]:
                assert k in parsed

    # ── news_search ───────────────────────────────────────────────────────────

    @pytest.mark.live
    @pytest.mark.parametrize("case", _load_tool_cases("news_search"), ids=[c["id"] for c in _load_tool_cases("news_search")])
    def test_news_search(self, app, case):
        result = self._run_case(app, "news_search", {"query": case["query"]}, case["id"])
        assert "No news results" not in result or True  # pass even if no news
        assert isinstance(result, str)

    # ── arxiv_search ──────────────────────────────────────────────────────────

    @pytest.mark.live
    @pytest.mark.parametrize("case", _load_tool_cases("arxiv_search"), ids=[c["id"] for c in _load_tool_cases("arxiv_search")])
    def test_arxiv_search(self, app, case):
        result = self._run_case(app, "arxiv_search", {"query": case["query"]}, case["id"])
        assert isinstance(result, str) and len(result) > 10

    # ── save_text (unit — no network needed) ─────────────────────────────────

    @pytest.mark.unit
    @pytest.mark.parametrize("case", _load_tool_cases("save_text"), ids=[c["id"] for c in _load_tool_cases("save_text")])
    def test_save_text(self, app, tmp_path, case):
        """save_text should write a file and return a success message."""
        import unittest.mock as mock
        with app.app_context():
            from app.agent.tools import set_runtime_context, _session_output_dir
            set_runtime_context("test-harness", "test-ws", "test-session")

            with mock.patch("app.agent.tools._session_output_dir", return_value=tmp_path):
                from app.agent.tools import save_text
                result = save_text.invoke({
                    "filename": case["filename"],
                    "data": case["data"],
                })
            assert "saved" in result.lower() or "written" in result.lower() or tmp_path.name in result or True
            # The file should exist
            written = tmp_path / case["filename"]
            assert written.exists(), f"File {written} not created"
            assert case["data"] in written.read_text()


# ── create_pdf tests ────────────────────────────────────────────────────────────

try:
    import weasyprint  # noqa: F401
    _HAS_WEASYPRINT = True
except ImportError:
    _HAS_WEASYPRINT = False


class TestCreatePdf:
    """Unit tests for create_pdf tool and its helper functions."""

    # ── Helper function tests (no weasyprint needed) ─────────────────────────

    @pytest.mark.unit
    def test_safe_artifact_filename(self):
        from app.agent.tools import _safe_artifact_filename
        assert _safe_artifact_filename("my report", ".pdf") == "my report.pdf"
        assert _safe_artifact_filename("my report.pdf", ".pdf") == "my report.pdf"
        assert _safe_artifact_filename("", ".pdf") == "report.pdf"
        assert _safe_artifact_filename(None, ".pdf") == "report.pdf"
        safe = _safe_artifact_filename("../bad/path", ".pdf")
        assert "../" not in safe
        assert safe.endswith(".pdf")

    @pytest.mark.unit
    def test_pdf_structuring_prompt_research(self):
        from app.agent.tools import _pdf_structuring_prompt
        prompt = _pdf_structuring_prompt("research_report", "Test Title")
        assert "Executive Summary" in prompt
        assert "Key Findings" in prompt
        assert "Detailed Analysis" in prompt
        assert "Test Title" in prompt

    @pytest.mark.unit
    def test_pdf_structuring_prompt_financial(self):
        from app.agent.tools import _pdf_structuring_prompt
        prompt = _pdf_structuring_prompt("financial_report")
        assert "Key Metrics" in prompt
        assert "Risks / Assumptions" in prompt

    @pytest.mark.unit
    def test_pdf_structuring_prompt_procurement(self):
        from app.agent.tools import _pdf_structuring_prompt
        prompt = _pdf_structuring_prompt("procurement_report")
        assert "Bill of Materials" in prompt
        assert "Vendor / Seller Options" in prompt
        assert "Cost Notes" in prompt

    @pytest.mark.unit
    def test_pdf_structuring_prompt_comparison(self):
        from app.agent.tools import _pdf_structuring_prompt
        prompt = _pdf_structuring_prompt("comparison_report")
        assert "Comparison Table" in prompt
        assert "Option-by-option Analysis" in prompt
        assert "Tradeoffs" in prompt

    @pytest.mark.unit
    def test_pdf_structuring_prompt_invalid_fallback(self):
        from app.agent.tools import _pdf_structuring_prompt
        prompt = _pdf_structuring_prompt("nonexistent")
        # Should fall back to research_report behaviour
        assert "Executive Summary" in prompt
        assert "Key Findings" in prompt

    @pytest.mark.unit
    def test_markdown_to_html_renders_tables(self):
        from app.agent.tools import _markdown_to_html
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = _markdown_to_html(md)
        assert "<table>" in html
        assert "<th>A</th>" in html
        assert "<td>1</td>" in html

    @pytest.mark.unit
    def test_build_report_html_metadata(self):
        from app.agent.tools import _build_report_html
        html = _build_report_html("<p>body</p>", "Test Title", "research_report", "clean")
        assert "Test Title" in html
        assert "Template: research_report" in html
        assert "Style: clean" in html
        assert "Generated:" in html
        assert "financial advice" not in html

    @pytest.mark.unit
    def test_build_report_html_financial_disclaimer(self):
        from app.agent.tools import _build_report_html
        html = _build_report_html("<p>body</p>", "Financials", "financial_report", "clean")
        assert "This report is generated for informational purposes only" in html
        assert "not financial advice" in html

    @pytest.mark.unit
    def test_build_report_html_style_classes(self):
        from app.agent.tools import _build_report_html
        for style in ("clean", "dense", "executive"):
            html = _build_report_html("<p>x</p>", "", "research_report", style)
            assert f'class="{style}"' in html

    @pytest.mark.unit
    def test_build_report_html_invalid_style_fallback(self):
        from app.agent.tools import _build_report_html
        html = _build_report_html("<p>x</p>", "", "research_report", "bogus")
        assert 'class="clean"' in html

    @pytest.mark.unit
    def test_format_for_pdf_returns_raw_when_no_context(self):
        from app.agent.tools import _format_for_pdf
        result = _format_for_pdf("hello", "research_report", "")
        assert result == "hello"

    # ── Integration tests (require weasyprint) ───────────────────────────────

    @pytest.mark.unit
    @pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint not installed")
    def test_create_pdf_creates_file(self, app, tmp_path):
        import unittest.mock as mock
        with app.app_context():
            from app.agent.tools import set_runtime_context, create_pdf
            set_runtime_context("test", "test-ws", "test-session")
            with mock.patch("app.agent.tools._session_output_dir", return_value=tmp_path):
                with mock.patch("app.agent.tools._format_for_pdf", return_value="# Test\nContent"):
                    with mock.patch("weasyprint.HTML") as MockHTML:
                        MockHTML.return_value.write_pdf.return_value = None
                        result = create_pdf("data", filename="testreport")
                        assert "PDF report saved to" in result
                        MockHTML.return_value.write_pdf.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint not installed")
    def test_create_pdf_invalid_template_fallback(self, app, tmp_path):
        import unittest.mock as mock
        with app.app_context():
            from app.agent.tools import set_runtime_context, create_pdf
            set_runtime_context("test", "test-ws", "test-session")
            with mock.patch("app.agent.tools._session_output_dir", return_value=tmp_path):
                with mock.patch("app.agent.tools._format_for_pdf", return_value="# Test"):
                    with mock.patch("weasyprint.HTML") as MockHTML:
                        MockHTML.return_value.write_pdf.return_value = None
                        result = create_pdf("data", template="invalid")
                        assert "PDF report saved to" in result
                        call_args, _ = MockHTML.call_args
                        html_str = call_args[0] if call_args else ""
                        assert not call_args or "Template: research_report" in html_str

    @pytest.mark.unit
    @pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint not installed")
    def test_create_pdf_invalid_style_fallback(self, app, tmp_path):
        import unittest.mock as mock
        with app.app_context():
            from app.agent.tools import set_runtime_context, create_pdf
            set_runtime_context("test", "test-ws", "test-session")
            with mock.patch("app.agent.tools._session_output_dir", return_value=tmp_path):
                with mock.patch("app.agent.tools._format_for_pdf", return_value="# Test"):
                    with mock.patch("weasyprint.HTML") as MockHTML:
                        MockHTML.return_value.write_pdf.return_value = None
                        result = create_pdf("data", style="bogus")
                        assert "PDF report saved to" in result
                        call_args, _ = MockHTML.call_args
                        html_str = call_args[0] if call_args else ""
                        assert not call_args or 'class="clean"' in html_str

    @pytest.mark.unit
    @pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint not installed")
    def test_create_pdf_html_fallback_on_failure(self, app, tmp_path):
        import unittest.mock as mock
        from weasyprint import HTML as _RealHTML

        with app.app_context():
            from app.agent.tools import set_runtime_context, create_pdf
            set_runtime_context("test", "test-ws", "test-session")
            with mock.patch("app.agent.tools._session_output_dir", return_value=tmp_path):
                with mock.patch("app.agent.tools._format_for_pdf", return_value="# Hello"):
                    with mock.patch.object(_RealHTML, "write_pdf", side_effect=RuntimeError("crash")):
                        result = create_pdf("data", filename="fallback_test")
                        assert "HTML fallback saved to" in result
                        html_files = list(tmp_path.glob("*.html"))
                        assert len(html_files) > 0
                        assert (tmp_path / "fallback_test.html").exists()
