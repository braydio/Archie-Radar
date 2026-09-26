from app.connectors.orange_county import OrangeCountyFoundCatsConnector


HTML = """
<html><body>
<div class="pet-card">
  <img alt="Image_A253398" src="/image/123456" />
  <p>Gender: Male</p>
  <p>Days Since Found: 6</p>
  <p>Status: Found and at the Finder's Home</p>
  <p>Location Found: Near Dennys</p>
  <p>Breed: Domestic Shorthair</p>
</div>
<div class="pet-card">
  <img alt="Image_A253452" src="/image/999999" />
  <p>Gender: Unknown Gender</p>
  <p>Days Since Found: 3</p>
  <p>Status: Found and at the Finder's Home</p>
  <p>Location Found: High St, Carrboro, Nc</p>
  <p>Breed: American Shorthair</p>
</div>
</body></html>
"""


def test_orange_found_reports_parse():
    rows = OrangeCountyFoundCatsConnector.parse_listing(HTML, "https://24petconnect.com/ORNCFoundReports?at=CAT")
    assert len(rows) == 2
    assert rows[0].source == "orange_county_found"
    assert rows[0].source_id == "A253398"
    assert rows[0].sex == "male"
    assert rows[0].location_text == "Near Dennys"
    assert rows[0].raw["geocode_context"].startswith("Orange County")
    assert rows[0].raw["source_platform"] == "24PetConnect"
    assert rows[0].raw["custody_type"] == "finder"
    assert rows[0].raw["custody_label"] == "With finder"
    assert rows[1].sex == "unknown"
