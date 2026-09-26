from app.connectors.aps_durham import APSDurhamFoundPetsConnector


def test_parse_archive_links():
    html = '''<a href="/found-pets/found-09-25-2026/">Found cat</a><a href="/found-pets/">Archive</a>'''
    assert APSDurhamFoundPetsConnector.parse_archive_links(html, 'https://www.apsofdurham.org/found-pets/') == [
        'https://www.apsofdurham.org/found-pets/found-09-25-2026/'
    ]


def test_parse_cat_detail():
    html = '''
    <html><body><h3>Found 09/25/2026</h3><p>Domestic Shorthair</p><ul><li>adult</li><li>male</li></ul>
    <div>Fur Type\nshort</div><div>Fur Color\ngray and white</div><div>Identifying Marks\nwhite chin</div>
    <div>Found Near\nHope Valley Road</div><div>Found On Date\n09/25/2026</div>
    <img src="/uploads/cat.jpg" alt="cat"></body></html>
    '''
    row = APSDurhamFoundPetsConnector.parse_detail(html, 'https://www.apsofdurham.org/found-pets/found-09-25-2026/')
    assert row is not None
    assert row.species == 'cat'
    assert row.sex == 'male'
    assert row.location_text == 'Hope Valley Road'
    assert row.image_url.endswith('/uploads/cat.jpg')
