from io import BytesIO

from PIL import Image, ImageDraw

from app.matcher import score_candidate
from app.models import ArchieProfile
from app.schemas import PetPostIn
from app.vision import compare_fingerprints, fingerprint_image, looks_like_placeholder_image


def make_gradient(reverse=False):
    image = Image.new("RGB", (96, 64))
    for y in range(64):
        for x in range(96):
            v = int((x / 95) * 255)
            if reverse:
                v = 255 - v
            image.putpixel((x, y), (v, 80 + y, 140))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_same_photo_fingerprint_is_near_one():
    data = make_gradient()
    a = fingerprint_image(data)
    b = fingerprint_image(data)
    assert compare_fingerprints(a.dhash, a.color_histogram, b.dhash, b.color_histogram) > 0.99


def test_different_gradient_scores_lower():
    a = fingerprint_image(make_gradient())
    b = fingerprint_image(make_gradient(reverse=True))
    similarity = compare_fingerprints(a.dhash, a.color_histogram, b.dhash, b.color_histogram)
    assert similarity < 0.8


def test_strong_reference_likeness_boosts_triage_score():
    profile = ArchieProfile(id=1, species="cat", sex="male", altered_status="neutered")
    post = PetPostIn(source="x", source_id="1", sex="male")
    base, _ = score_candidate(post, profile)
    with_photo, reasons = score_candidate(post, profile, 0.95)
    assert with_photo > base
    assert any("reference-photo likeness" in r for r in reasons)


def test_low_information_placeholder_is_ignored():
    image = Image.new("RGB", (320, 240), "#deddd6")
    draw = ImageDraw.Draw(image)
    draw.line((0, 0, 320, 240), fill="white", width=28)
    draw.line((320, 0, 0, 240), fill="white", width=28)
    buf = BytesIO()
    image.save(buf, format="PNG")
    assert looks_like_placeholder_image(buf.getvalue()) is True


def test_realish_gradient_is_not_placeholder():
    assert looks_like_placeholder_image(make_gradient()) is False
