import re


CAT_WORDS = re.compile(r"\b(cat|cats|kitten|kittens|kitty|kitties|feline|tabby|calico|meow)\b", re.I)
DOG_ONLY = re.compile(r"\b(dog|dogs|puppy|puppies)\b", re.I)
IRRELEVANT = re.compile(r"\b(vet special|adoption event|fundraiser|rabies clinic|sponsorship|business hours)\b", re.I)


def is_cat_related(text: str) -> bool:
    value = text or ""
    if not CAT_WORDS.search(value):
        return False
    if IRRELEVANT.search(value) and not re.search(r"\b(found|lost|missing|stray|sighting|seen|wandering)\b", value, re.I):
        return False
    return True


def candidate_status(text: str) -> str:
    value = (text or "").lower()
    if re.search(r"\b(lost|missing|escaped|ran away)\b", value):
        return "lost"
    if re.search(r"\b(found|stray|wandering|sighting|seen)\b", value):
        return "found"
    return "unknown"
