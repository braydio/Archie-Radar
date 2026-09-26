from datetime import datetime, timezone

from app.connectors.base import extract_source_posted_at


def test_extract_source_posted_at_prefers_page_publication_metadata():
    html = '''
    <html><head>
      <meta property="article:published_time" content="2026-09-25T14:23:00-04:00">
      <meta property="article:modified_time" content="2026-09-25T15:10:00-04:00">
    </head><body><time datetime="2026-09-25T14:23:00-04:00">today</time></body></html>
    '''
    value = extract_source_posted_at(html)
    assert value == datetime(2026, 9, 25, 18, 23, tzinfo=timezone.utc)


def test_extract_source_posted_at_reads_json_ld():
    html = '''
    <script type="application/ld+json">
      {"@type":"Article","datePublished":"2026-07-03T10:30:00Z"}
    </script>
    '''
    assert extract_source_posted_at(html) == datetime(2026, 7, 3, 10, 30, tzinfo=timezone.utc)
