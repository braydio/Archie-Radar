from app.connectors.pet911 import Pet911Connector


def test_parse_pet911_found_cat():
    html = '''
    <article><a href="/chapel-hill/found/123">Found cat, Franklin Street</a>
    <img src="/cat.jpg"><div>Found</div><div>Found cat, Franklin Street, Chapel Hill</div>
    <div>Franklin Street, Chapel Hill</div><div>Friendly gray male cat with white chest.</div>
    <div>25.09.2026</div></article>
    '''
    rows = Pet911Connector.parse_listing(html, 'https://pet911.org/chapel-hill/found')
    assert len(rows) == 1
    assert rows[0].sex == 'male'
    assert 'Franklin Street' in rows[0].location_text
    assert rows[0].image_url == 'https://pet911.org/cat.jpg'
