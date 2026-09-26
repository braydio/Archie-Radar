from app.connectors.regional_24petconnect import Regional24PetConnectConnector


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
    assert rows[1].source == 'burlington_24petconnect'
    assert rows[1].altered_status == 'spayed'
