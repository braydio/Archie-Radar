from app.connectors.pawboost import PawBoostConnector


HTML = """
<html><body>
Reported 3 weeks ago
Found Pet Male Cat
FOUND PawBoost ID: 73228055
Raleigh, NC 27609
Black cat with short hair and a fluffy tail.
View On Facebook
Reported 1 month ago
Found Pet Unknown Cat
SIGHTING PawBoost ID: 73182553
Durham, NC 27713
Grey no collar
View Pet
Reported 2 hours ago
Shelter Intake Male Cat
SHELTER INTAKE PawBoost ID: 73300041
1601 Eubanks Rd, Chapel Hill, NC 27516, USA
Orange County Animal Services
Large gray tabby Domestic Shorthair
</body></html>
"""


def test_parser_extracts_ids_status_location_and_shelter_intakes():
    rows = PawBoostConnector.parse_listing(HTML, "https://example.test")
    assert len(rows) == 3
    assert rows[0].source_id == "73228055"
    assert rows[0].status == "found"
    assert rows[0].sex == "male"
    assert rows[0].location_text == "Raleigh, NC 27609"
    assert rows[1].status == "sighting"
    assert rows[2].status == "shelter_intake"
    assert rows[2].sex == "male"
    assert rows[2].location_text == "1601 Eubanks Rd, Chapel Hill, NC 27516, USA"


def test_regional_url_uses_area_slug():
    connector = PawBoostConnector(["pittsboro-nc-27312"], pages=1)
    assert "pittsboro-nc-27312" in connector._url("pittsboro-nc-27312", 1)


def test_detail_page_enriches_actual_photo_and_finder_fields():
    post = PawBoostConnector.parse_listing(HTML, "https://www.pawboost.com/lost-found-pets/sanford-nc-27330/all-found-stray-cats/page-1")[0]
    detail = """
    <html><body>
      <div class="col-md-5 padding-outer-offset">
        <div class="pet-details-featured margin-bottom-0">
          <img alt="Found/Stray Male Cat last seen Winding ridge, Sanford, NC 27332"
               src="https://img-cdn.pawboost.com/1785106706/16227.jpg"
               class="no-padding pet-details-featured-image width-full">
        </div>
      </div>
      <div>Status</div><div>FOUND</div>
      <div>Date Found</div><div>July 25, 2026</div>
      <div>Location Found</div><div>Sanford, NC 27332</div>
      <div>Nearest Landmark</div><div>Winding ridge</div>
      <div>Sex</div><div>Male</div>
      <div>PawBoost ID</div><div>73188404</div>
      <div>Description</div><div>Grey tabby about a year old friendly.</div>
      <div>Message from Finder</div><div>Please contact me if this is your cat.</div>
      <div>CONTACT FINDER</div>
    </body></html>
    """
    enriched = PawBoostConnector.enrich_from_detail(
        post,
        detail,
        "https://www.pawboost.com/landing/pet/example/found-stray-thispet-sanford-nc-27332",
    )
    assert enriched.image_url == "https://img-cdn.pawboost.com/1785106706/16227.jpg"
    assert enriched.location_text == "Sanford, NC 27332"
    assert enriched.sex == "male"
    assert enriched.description == "Grey tabby about a year old friendly."
    assert enriched.raw["nearest_landmark"] == "Winding ridge"
    assert enriched.raw["contact_available"] is True
    assert enriched.raw["image_confirmed_missing"] is False


def test_detail_page_can_confirm_no_real_image():
    post = PawBoostConnector.parse_listing(HTML, "https://example.test")[0]
    detail = """
    <html><body>
      <div>Status</div><div>FOUND</div>
      <div>PawBoost ID</div><div>73228055</div>
      <div>Sex</div><div>Male</div>
    </body></html>
    """
    enriched = PawBoostConnector.enrich_from_detail(post, detail, "https://example.test/landing/pet/x")
    assert enriched.raw["detail_page_enriched"] is True
    assert enriched.raw["image_confirmed_missing"] is True
