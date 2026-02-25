from flask import Flask, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import re

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Static product catalogue (excludes Tools & Accessories and Equipment)
# Live URL format:  https://htspoly.com/product/{slug}
# Micro URL format: https://qr.htspoly.com/{slug}
# ---------------------------------------------------------------------------
PRODUCTS = {
    "Polyurea Joint Fill": [
        {"name": "PE-45",  "live": "https://htspoly.com/product/pe-45",  "micro": "https://qr.htspoly.com/pe-45"},
        {"name": "PE-65",  "live": "https://htspoly.com/product/pe-65",  "micro": "https://qr.htspoly.com/pe-65"},
        {"name": "PE-85",  "live": "https://htspoly.com/product/pe-85",  "micro": "https://qr.htspoly.com/pe-85"},
        {"name": "PE-90",  "live": "https://htspoly.com/product/pe-90",  "micro": "https://qr.htspoly.com/pe-90"},
    ],
    "Concrete Repair": [
        {"name": "TX-1",   "live": "https://htspoly.com/product/tx-1",   "micro": "https://qr.htspoly.com/tx-1"},
        {"name": "TX-2",   "live": "https://htspoly.com/product/tx-2",   "micro": "https://qr.htspoly.com/tx-2"},
        {"name": "TX-3",   "live": "https://htspoly.com/product/tx-3",   "micro": "https://qr.htspoly.com/tx-3"},
        {"name": "TX-GEL", "live": "https://htspoly.com/product/tx-gel", "micro": "https://qr.htspoly.com/tx-gel"},
        {"name": "TX-PMF", "live": "https://htspoly.com/product/tx-pmf", "micro": "https://qr.htspoly.com/tx-pmf"},
        {"name": "TX-UV",  "live": "https://htspoly.com/product/tx-uv",  "micro": "https://qr.htspoly.com/tx-uv"},
    ],
    "Densifiers & Sealers": [
        {"name": "CD-HS",    "subsection": "Densifiers", "live": "https://htspoly.com/product/cd-hs",    "micro": "https://qr.htspoly.com/cd-hs"},
        {"name": "CD-HSL",   "subsection": "Densifiers", "live": "https://htspoly.com/product/cd-hsl",   "micro": "https://qr.htspoly.com/cd-hsl"},
        {"name": "CD-LS",    "subsection": "Densifiers", "live": "https://htspoly.com/product/cd-ls",    "micro": "https://qr.htspoly.com/cd-ls"},
        {"name": "CD-SS",    "subsection": "Densifiers", "live": "https://htspoly.com/product/cd-ss",    "micro": "https://qr.htspoly.com/cd-ss"},
        {"name": "CS-PS",    "subsection": "Sealers",    "live": "https://htspoly.com/product/cs-ps",    "micro": "https://qr.htspoly.com/cs-ps"},
        {"name": "CS-PS SV", "subsection": "Sealers",    "live": "https://htspoly.com/product/cs-ps-sv", "micro": "https://qr.htspoly.com/cs-pssv"},
        {"name": "CS-HG",    "subsection": "Sealers",    "live": "https://htspoly.com/product/cs-hg",    "micro": "https://qr.htspoly.com/cs-hg"},
        {"name": "CS-AC30",  "subsection": "Sealers",    "live": "https://htspoly.com/product/cs-ac30",  "micro": "https://qr.htspoly.com/cs-ac30"},
    ],
    "Floor Coatings": [
        {"name": "EPX-60 WB",  "subsection": "Epoxy",        "live": "https://htspoly.com/product/epx-60wb",  "micro": "https://qr.htspoly.com/epx-60wb"},
        {"name": "EPX-100",    "subsection": "Epoxy",        "live": "https://htspoly.com/product/epx-100",    "micro": "https://qr.htspoly.com/epx-100"},
        {"name": "EPX-100 HV", "subsection": "Epoxy",        "live": "https://htspoly.com/product/epx-100hv", "micro": "https://qr.htspoly.com/epx-100hv"},
        {"name": "PMR-60 WB",  "subsection": "Epoxy",        "live": "https://htspoly.com/product/pmr-60wb",  "micro": "https://qr.htspoly.com/pmr-60wb"},
        {"name": "PMR-100",    "subsection": "Epoxy",        "live": "https://htspoly.com/product/pmr-100",    "micro": "https://qr.htspoly.com/pmr-100"},
        {"name": "PAS-100",    "subsection": "Polyaspartic", "live": "https://htspoly.com/product/pas-100",    "micro": "https://qr.htspoly.com/pas-100"},
        {"name": "PAS-200",    "subsection": "Polyaspartic", "live": "https://htspoly.com/product/pas-200",    "micro": "https://qr.htspoly.com/pas-200"},
        {"name": "MCU-ST",     "subsection": "Urethane",     "live": "https://htspoly.com/product/mcu-st",     "micro": "https://qr.htspoly.com/mcu-st"},
        {"name": "MCU-MT",     "subsection": "Urethane",     "live": "https://htspoly.com/product/mcu-mt",     "micro": "https://qr.htspoly.com/mcu-mt"},
        {"name": "MCU-HG",     "subsection": "Urethane",     "live": "https://htspoly.com/product/mcu-hg",     "micro": "https://qr.htspoly.com/mcu-hg"},
    ],
}

DOC_PATTERN = re.compile(r'\.(pdf|doc|docx)(\?[^#]*)?$', re.IGNORECASE)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LinkScout/1.0)"}


def normalize_href(href: str) -> str:
    """Decode percent-encoding so (us) and %28us%29 compare as equal."""
    return unquote(href).lower().rstrip("/")


IGNORE_HREFS = {
    "https://htspoly.com/assets/hts-credit-application.pdf",
}


def is_doc_link(href: str) -> bool:
    return bool(DOC_PATTERN.search(urlparse(href).path))


def find_link_title(tag) -> str:
    """Walk up the DOM from a link tag to find a nearby label/heading."""
    node = tag
    for _ in range(5):
        parent = node.parent
        if parent is None:
            break
        for sib in node.previous_siblings:
            # Skip other <a> tags — they're sibling links, not titles
            if getattr(sib, "name", None) == "a":
                continue
            if hasattr(sib, "get_text"):
                text = sib.get_text(strip=True)
            else:
                text = str(sib).strip()
            if text and len(text) > 2:
                return text.splitlines()[0].strip()
        node = parent
    return ""


def fetch_doc_links(url: str) -> dict:
    """Fetch a page and return all .pdf / .doc / .docx link hrefs."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        seen: set = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            absolute = urljoin(url, href)
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https") and is_doc_link(absolute):
                if absolute not in seen and normalize_href(absolute) not in {normalize_href(h) for h in IGNORE_HREFS}:
                    seen.add(absolute)
                    links.append({
                        "title": find_link_title(tag),
                        "text": tag.get_text(strip=True) or "(no text)",
                        "href": absolute,
                    })
        return {"url": url, "links": links, "error": None}
    except Exception as exc:
        return {"url": url, "links": [], "error": str(exc)}


def compare_product(product: dict) -> dict:
    live_data  = fetch_doc_links(product["live"])
    micro_data = fetch_doc_links(product["micro"])

    # Build norm→original and norm→text mappings for each side
    live_norm  = {normalize_href(l["href"]): l for l in live_data["links"]}
    micro_norm = {normalize_href(l["href"]): l for l in micro_data["links"]}

    live_keys  = set(live_norm)
    micro_keys = set(micro_norm)

    matched_keys       = live_keys & micro_keys
    missing_keys       = live_keys - micro_keys
    extra_keys         = micro_keys - live_keys

    matched            = sorted(live_norm[k]["href"]  for k in matched_keys)
    missing_from_micro = sorted(live_norm[k]["href"]  for k in missing_keys)
    extra_on_micro     = sorted(micro_norm[k]["href"] for k in extra_keys)

    if live_data["error"] or micro_data["error"]:
        status = "error"
    elif not live_keys:
        status = "no_docs"
    elif missing_keys:
        status = "mismatch"
    else:
        status = "ok"

    return {
        "name":               product["name"],
        "live":               product["live"],
        "micro":              product["micro"],
        "live_error":         live_data["error"],
        "micro_error":        micro_data["error"],
        "live_links":         [live_norm[k]  for k in sorted(live_keys)],
        "micro_links":        [micro_norm[k] for k in sorted(micro_keys)],
        "matched":            matched,
        "missing_from_micro": missing_from_micro,
        "extra_on_micro":     extra_on_micro,
        "status":             status,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS)


@app.route("/products")
def get_products():
    return jsonify(PRODUCTS)


@app.route("/compare", methods=["POST"])
def compare():
    data = request.get_json()
    result = compare_product({
        "name":  data.get("name", ""),
        "live":  data.get("live", ""),
        "micro": data.get("micro", ""),
    })
    return jsonify(result)


@app.route("/compare-all", methods=["POST"])
def compare_all():
    results = {}
    for section, products in PRODUCTS.items():
        results[section] = [compare_product(p) for p in products]
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
