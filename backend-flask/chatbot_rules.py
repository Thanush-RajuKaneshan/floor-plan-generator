"""Small, deterministic explanations for generated floor-plan output."""

import re


_GLOSSARY = {
    "DCPR": {
        "aliases": ("dcpr", "development control and promotion regulations"),
        "answer": (
            "DCPR means Development Control and Promotion Regulations. This project "
            "uses local Mumbai DCPR-2034 source material; the chatbot explains terms "
            "but does not decide whether a proposal will be approved."
        ),
    },
    "FSI": {
        "aliases": ("fsi", "floor space index"),
        "answer": (
            "FSI (Floor Space Index) is the ratio of the combined gross floor area "
            "of all floors, excluding areas specifically exempted by the regulations, "
            "to the plot area. The generator uses the FSI value supplied by the app "
            "to check the requested typical-floor layout. "
            "Source: Mumbai DCPR-2034, Regulation 2(IV)(61), local extract page 29."
        ),
    },
    "BUA": {
        "aliases": ("bua", "built up area", "built-up area"),
        "answer": (
            "BUA means built-up area. In this app, the estimated maximum BUA is "
            "calculated from plot area × FSI. The generated plan's total built area "
            "is its floor area × the entered number of floors. Regulatory exclusions "
            "can affect official calculations, so treat these as app estimates."
        ),
    },
    "BHK": {
        "aliases": ("bhk", "1 bhk", "2 bhk", "3 bhk", "4 bhk"),
        "answer": (
            "BHK is a common housing label for the number of bedrooms: for example, "
            "2 BHK means a home with two bedrooms. It is a room-count label, not a "
            "promise that the generated room sizes meet a legal standard."
        ),
    },
    "plot area": {
        "aliases": ("plot area", "site area", "land area"),
        "answer": (
            "Plot area is the land area used by the app for its area and FSI "
            "estimates. The submitted boundary image supplies the plot's shape; the "
            "area entered in the form sets its scale."
        ),
    },
    "ground coverage": {
        "aliases": ("ground coverage", "coverage"),
        "answer": (
            "Ground coverage is the share of the plot occupied by the generated "
            "floorplate. This app checks its concept against a 65% cap; that check "
            "is a generator constraint, not confirmation of the site's DCPR limit."
        ),
    },
    "setback": {
        "aliases": ("setback", "set backs", "margin"),
        "answer": (
            "A setback is the space between a plot boundary and a building. This "
            "generator uses a 2 m inset for its concept envelope, falling back to "
            "1 m if the larger inset is too small. These fixed values are not a "
            "site-specific DCPR setback determination."
        ),
    },
    "building envelope": {
        "aliases": ("building envelope", "envelope"),
        "answer": (
            "The building envelope is the inset polygon in which this generator "
            "tries to place the floorplate. It is created using the generator's "
            "fixed 2 m setback, with a 1 m fallback; it is not a surveyed or "
            "authority-approved buildable boundary."
        ),
    },
    "typical floor": {
        "aliases": ("typical floor", "floor plan per floor"),
        "answer": (
            "A typical floor is one representative arrangement of apartments and "
            "shared circulation. The app repeats that floorplate for the entered "
            "floor count when it calculates total built area."
        ),
    },
    "design variants": {
        "aliases": ("design variant", "design variants", "variants", "alternatives"),
        "answer": (
            "The app creates three concepts by searching apartment arrangements "
            "(kitchen on the facade or by the entry, mirrored, alternative "
            "proportions) and keeping the best-scoring ones against design rules. "
            "They are rule-checked concepts, not code-certified designs."
        ),
    },
    "corridor": {
        "aliases": ("corridor", "common corridor", "hallway"),
        "answer": (
            "The common corridor connects the apartments to the shared circulation "
            "core. The generator models it as 1.8 m wide; have a licensed architect "
            "check the applicable requirements for a real project."
        ),
    },
    "circulation core": {
        "aliases": ("circulation core", "staircase", "lift", "elevator"),
        "answer": (
            "The shared circulation core is the common area containing the "
            "staircase, lift, and lobby. Its geometry is part of the generated "
            "concept and is not a fire-safety or accessibility approval."
        ),
    },
    "json": {
        "aliases": ("json", "json file"),
        "answer": (
            "The JSON download contains the generated room polygons, boundaries, "
            "areas, apartment details, and generation metadata in structured form."
        ),
    },
    "dxf": {
        "aliases": ("dxf", "dxf file", "cad file"),
        "answer": (
            "DXF is a CAD drawing format. This app exports the generated concept "
            "geometry so it can be opened in compatible CAD software; it is not a "
            "construction or sanctioned drawing."
        ),
    },
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def answer_question(message: str) -> str:
    """Answer supported output and glossary questions without a model."""

    question = _normalize(message)
    if not question:
        return "Ask me about the generated plan, its metrics, or a DCPR term."

    if any(phrase in question for phrase in (
        "how is the plan generated",
        "how are plans generated",
        "how does generation work",
        "how does this generate",
        "what does the output show",
        "explain the output",
    )):
        return (
            "The app extracts a plot outline from your image, scales it to the plot "
            "area you entered, then places apartment rooms and a shared corridor, "
            "staircase, lift, and lobby inside an inset envelope. It checks basic "
            "geometry and the entered FSI/coverage constraints, then produces three "
            "floor-plan concepts. These are preliminary concepts, not DCPR approvals "
            "or construction-ready plans."
        )

    for term, details in _GLOSSARY.items():
        for alias in sorted(details["aliases"], key=len, reverse=True):
            normalized_alias = _normalize(alias)
            if f" {normalized_alias} " in f" {question} ":
                return details["answer"]

    if question in {"hi", "hello", "hey", "help", "what can you explain"}:
        return (
            "I can explain the generated floor-plan output and terms such as FSI, "
            "BUA, BHK, setbacks, ground coverage, and DCPR. Ask about one of those "
            "or how the three plan concepts are produced."
        )

    return (
        "I don't have a verified rule for that question. I can explain the "
        "generated plan and its metrics, or define terms such as FSI, BUA, BHK, "
        "setback, ground coverage, and DCPR. I won't guess at site-specific "
        "regulatory advice."
    )
