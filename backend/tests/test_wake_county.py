from app.connectors.wake_county import WakeCountyLostFoundConnector


def test_parse_wake_listing_and_detail():
    listing = '''
    <div class="card"><img src="/img/272500.jpg"><a href="/lostfound/272500">Mittens</a>
    <span>272500 - Male</span><span>Age: 4 Years</span><span>Date In Shelter: 9/25/2026</span></div>
    '''
    rows = WakeCountyLostFoundConnector.parse_listing(listing, 'https://pets.wake.gov/lostfound')
    assert len(rows) == 1
    assert rows[0].source_id == '272500'
    assert rows[0].sex == 'male'
    detail = '''<h1>Mittens 272500</h1><p>Breed: Domestic Shorthair</p><p>Male</p>
    <p>Spayed/Neutered: Yes</p><p>Location: Main Shelter</p><p>Date In Shelter: 9/25/2026</p>
    <img alt="272500 Mittens" src="/img/272500.jpg">'''
    row = WakeCountyLostFoundConnector.parse_detail(detail, 'https://pets.wake.gov/lostfound/272500', '272500')
    assert row is not None
    assert row.species == 'cat'
    assert row.altered_status == 'neutered'
