from app.connectors.regional_24petconnect import Regional24PetConnectConnector
import asyncio

import httpx


def test_parse_regional_24petconnect_sources_and_cats():
    html = '''
    <div>Animal id: A564184</div><img alt="Image: A564184" src="/a.jpg">
    <div>Gender : Male (Neutered)</div>
    <div>Days At Shelter : 0</div>
    <div>Status : Found and in Shelter Care (Animal Protection Society of Durham)</div>
    <div>Location Found : W Trinity Ave</div><div>Breed : Domestic Shorthair</div>
    <div>Animal id: A182751</div><div>Gender : Female (Spayed)</div>
    <div>Days At Shelter : 5</div>
    <div>Status : Found and in Shelter Care (Burlington Animal Services Pet Adoption & Resource Center)</div>
    <div>Location Found : 2000 Block Edgewood Ave</div><div>Breed : Domestic Shorthair</div>
    <div>Animal id: D1</div><div>Gender : Male</div><div>Status : Found and in Shelter Care (Some Shelter)</div>
    <div>Breed : Labrador Retriever</div>
    '''
    rows = Regional24PetConnectConnector.parse_listing(html, 'https://24petconnect.com/ViewAnimals/1')
    assert len(rows) == 2
    assert rows[0].source == 'durham_24petconnect'
    assert rows[0].sex == 'male'
    assert rows[0].altered_status == 'neutered'
    assert rows[0].image_url == 'https://24petconnect.com/a.jpg'
    assert rows[0].raw['source_link_kind'] == 'search_results'
    assert rows[0].source_url == 'https://24petconnect.com/ViewAnimals/1'
    assert rows[1].source == 'burlington_24petconnect'
    assert rows[1].altered_status == 'spayed'


def test_detail_link_is_extracted_only_from_matching_animal_card():
    html = '''
    <article><div>Animal id: A123</div><div>Status: Found</div><div>Location Found: Chapel Hill</div>
      <a href="/DetailsMain/DRHM/A123">Details</a></article>
    <article><div>Animal id: A999</div><div>Status: Found</div><div>Location Found: Durham</div>
      <a href="/DetailsMain/DRHM/A999">Details</a></article>
    '''
    rows = Regional24PetConnectConnector.parse_listing(html, 'https://24petconnect.com/ViewAnimals/77')
    assert [row.raw['detail_url'] for row in rows] == [
        'https://24petconnect.com/DetailsMain/DRHM/A123',
        'https://24petconnect.com/DetailsMain/DRHM/A999',
    ]
    assert all(row.raw['source_link_kind'] == 'exact_detail' for row in rows)


def test_detail_link_for_another_animal_is_rejected():
    html = '''<article><div>Animal id: A123</div><div>Status: Found</div>
      <a href="/DetailsMain/DRHM/A999">Details</a></article>'''
    row = Regional24PetConnectConnector.parse_listing(html, 'https://24petconnect.com/ViewAnimals/77')[0]
    assert row.raw['detail_url'] is None
    assert row.raw['source_link_kind'] == 'search_results'
    assert row.source_url == 'https://24petconnect.com/ViewAnimals/77'


def test_legacy_holder_fallback_uses_only_matching_source_key():
    assert Regional24PetConnectConnector.parse_24pet_context('', 'chatham_24petconnect')['holding_entity'] == 'Chatham County · Animal Resources Center'
    assert Regional24PetConnectConnector.parse_24pet_context('', 'regional_24petconnect')['holding_entity'] is None


def test_request_level_inactive_does_not_mark_animal_inactive():
    state, reason = Regional24PetConnectConnector.parse_animal_lifecycle(
        'Your request is currently Inactive. Animal ID A123. Status: Found and in Shelter Care.', 'A123')
    assert (state, reason) == ('active', None)


def test_animal_specific_terminal_state_is_preserved():
    state, reason = Regional24PetConnectConnector.parse_animal_lifecycle(
        'Animal ID A123. Animal status: Adopted.', 'A123')
    assert (state, reason) == ('inactive', 'adopted')


def test_broken_detail_url_does_not_remove_valid_result_row(monkeypatch):
    listing = '''<article><div>Animal id: A123</div><div>Status: Found</div>
      <div>Location Found: Chapel Hill</div><a href="/DetailsMain/DRHM/A123">Details</a></article>'''

    class Response:
        def __init__(self, url, text, fail=False):
            self.url, self.text, self.fail = url, text, fail

        def raise_for_status(self):
            if self.fail:
                request = httpx.Request('GET', self.url)
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError('not found', request=request, response=response)

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, url, **kwargs):
            if '/ViewAnimals/' in url:
                return Response(url, listing)
            return Response(url, '', fail=True)

    monkeypatch.setattr('app.connectors.regional_24petconnect.httpx.AsyncClient', lambda **kwargs: Client())
    rows = asyncio.run(Regional24PetConnectConnector('https://24petconnect.com/ViewAnimals/77').fetch())
    assert len(rows) == 1
    assert rows[0].source_id == 'A123'
    assert rows[0].raw['listing_state'] == 'active'
    assert rows[0].raw['source_link_kind'] == 'unavailable'
    assert rows[0].source_url == 'https://24petconnect.com/ViewAnimals/77'
