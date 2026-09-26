from app.connectors.petkey import PetkeyConnector


def test_parse_petkey_only_found_cats_and_no_microchip_storage():
    html = '''
    <h2>Shadow</h2>
    <div>Breed: Domestic Short Hair</div><div>Gender: Male</div><div>Age: 5 Years</div>
    <div>Microchip: 999999999</div><div>Other Id: 234555</div><div>Color: Gray white</div><div>Found 9/25/2026</div>
    <h2>Doggo</h2><div>Breed: Labrador Retriever</div><div>Gender: Male</div><div>Other Id: 234556</div><div>Found 9/25/2026</div>
    <h2>LostCat</h2><div>Breed: Domestic Shorthair</div><div>Other Id: 234557</div><div>Lost 9/25/2026</div>
    '''
    rows = PetkeyConnector.parse_listing(html, 'https://petkey.org/lost-and-found/chapel-hill_nc')
    assert len(rows) == 1
    assert rows[0].source_id == '234555'
    assert '999999999' not in str(rows[0].raw)
