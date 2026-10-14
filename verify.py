"""
verify.py: the checker for your research system.

Claude reads your sources and writes facts into claims.json. This script
trusts none of it. For every claim it checks:

  1. the source the claim points to is listed in sources.json
  2. the original file (in sources/) and its extracted text (in captures/)
     still match the fingerprints saved when the source was added, so
     nobody has changed either one since
  3. the quote appears word for word in the source's text (in captures/).
     Spacing, curly vs straight quotes and dash styles are ignored.
  4. the claimed value appears inside that quote

A claim that passes every check is "verified". A claim that fails any check
is "held", with the reason. Results go to REPORT.md.

Usage:
  python3 verify.py
      Check every claim and write REPORT.md.
  python3 verify.py fetch <address> --title "<title>"
      Download a public page or PDF into sources/ and register it.
  python3 verify.py paste <name> --title "<title>" --url "<address>"
      Save text pasted on standard input as sources/<name>.txt and register it.
      Use this when a site won't let scripts download it.
  python3 verify.py add sources/<file> --title "<title>" --url "<address>"
      Register a file that's already in sources/: save its fingerprint in
      sources.json and extract its text into captures/.

Python standard library only (PDF text extraction uses pdftotext or pypdf
if either is installed). Nothing in this file calls an AI model.
"""

import datetime
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).parent
SOURCES = HERE / "sources.json"
CLAIMS = HERE / "claims.json"
CAPTURES = HERE / "captures"
REPORT = HERE / "REPORT.md"


# ------------------------------------------------------------ helpers

def sha256_of(path):
    """A fingerprint of the file. Change one character and it changes completely."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


LOOKALIKES = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u202f": " ", "\u00ad": "",
})


def normalize(text):
    """Plain quotes and hyphens, single spaces. Applied to both sides equally."""
    return re.sub(r"\s+", " ", text.translate(LOOKALIKES)).strip()


NUMBER = r"\d[\d,]*(?:\.\d+)?"


def to_number(text):
    """'$1,234.5', '4.3%', '250,000 jobs' -> Decimal. None if no number."""
    match = re.search(NUMBER, str(text))
    if not match:
        return None
    try:
        return Decimal(match.group().replace(",", ""))
    except InvalidOperation:
        return None


def numbers_in(text):
    return [to_number(n) for n in re.findall(NUMBER, text)]


def load(path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8") or "[]")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "source"


# ------------------------------------------------------------ adding a source

def extract_text(path):
    """Return (text, extractor) or (None, reason)."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace"), "plain text"
    if suffix in (".html", ".htm"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        return html.unescape(re.sub(r"<[^>]+>", " ", raw)), "html tags removed"
    if suffix == ".pdf":
        if shutil.which("pdftotext"):
            out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                 capture_output=True, text=True)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout, "pdftotext -layout"
        try:
            import pypdf  # optional
            reader = pypdf.PdfReader(str(path))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return text, f"pypdf {pypdf.__version__}"
        except ImportError:
            pass
        return None, ("no PDF text extractor found. Install one with "
                      "'pip install pypdf' and run this command again.")
    return None, f"don't know how to read {suffix} files"


def add_source(args):
    if not args:
        sys.exit("usage: python3 verify.py add sources/<file> --title \"...\" --url \"...\"")
    path = (HERE / args[0]).resolve()
    if not path.exists():
        sys.exit(f"{args[0]} not found. Put the file in sources/ first.")
    if path.parent != (HERE / "sources").resolve():
        sys.exit("Originals live in sources/. Move the file there first.")
    opts = dict(zip(args[1::2], args[2::2]))
    title, url = opts.get("--title", path.stem), opts.get("--url", "")

    sources = load(SOURCES)
    original = f"sources/{path.name}"
    for s in sources:
        if s["original"] == original:
            sys.exit(f"{original} is already registered as '{s['id']}'. Nothing changed.")

    source_id = slug(path.stem)
    ids = {s["id"] for s in sources}
    n = 2
    while source_id in ids:
        source_id = f"{slug(path.stem)}-{n}"
        n += 1

    text, how = extract_text(path)
    if text is None:
        sys.exit(f"Couldn't extract text: {how}")
    capture = CAPTURES / f"{source_id}.txt"
    CAPTURES.mkdir(exist_ok=True)
    capture.write_text(text, encoding="utf-8")

    sources.append({
        "id": source_id,
        "title": title,
        "url": url,
        "original": original,
        "capture": f"captures/{capture.name}",
        "extractor": how,
        "sha256": sha256_of(path),
        "capture_sha256": sha256_of(capture),
        "added_on": datetime.date.today().isoformat(),
    })
    SOURCES.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    words = len(text.split())
    print(f"Added '{source_id}': {words:,} words extracted with {how}.")
    print(f"Fingerprint: {sources[-1]['sha256'][:16]}...")
    if words < 200 and path.suffix.lower() == ".pdf":
        print("Warning: very little text came out. The PDF may be scanned images.")


def fetch_source(args):
    if not args:
        sys.exit('usage: python3 verify.py fetch <address> --title "..."')
    url = args[0]
    opts = dict(zip(args[1::2], args[2::2]))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research-starter)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except Exception as e:
        sys.exit(f"Couldn't download {url}: {e}\n"
                 "If this is a claude.ai/code session, the environment's network access may "
                 "need to be set to Full. Otherwise copy the page text and use 'paste'.")
    if data[:4] == b"%PDF" or "pdf" in ctype:
        ext = ".pdf"
    elif "html" in ctype or data.lstrip()[:1] == b"<":
        ext = ".html"
    else:
        ext = ".txt"
    name = slug(Path(url.split("?")[0].rstrip("/")).stem or "source")
    path = HERE / "sources" / f"{name}{ext}"
    n = 2
    while path.exists():
        path = HERE / "sources" / f"{name}-{n}{ext}"
        n += 1
    path.write_bytes(data)
    print(f"Saved {len(data):,} bytes to sources/{path.name}")
    add_source([f"sources/{path.name}", "--title", opts.get("--title", name), "--url", url])


def paste_source(args):
    if not args:
        sys.exit('usage: python3 verify.py paste <name> --title "..." --url "..." < text')
    opts = dict(zip(args[1::2], args[2::2]))
    text = sys.stdin.read()
    if not text.strip():
        sys.exit("No text received. Pipe or paste the page text in.")
    path = HERE / "sources" / f"{slug(args[0])}.txt"
    if path.exists():
        sys.exit(f"sources/{path.name} already exists. Pick another name.")
    path.write_text(text, encoding="utf-8")
    add_source([f"sources/{path.name}", "--title", opts.get("--title", args[0]),
                "--url", opts.get("--url", "")])


# ------------------------------------------------------------ the checks

def check_claim(claim, sources):
    """Return ("verified", "") or ("held", reason)."""
    source = sources.get(claim.get("source_id", ""))
    if source is None:
        return "held", f"source '{claim.get('source_id', '')}' is not in sources.json"

    original = HERE / source["original"]
    if not original.exists():
        return "held", f"original file {source['original']} is missing"
    if sha256_of(original) != source["sha256"]:
        return "held", f"{source['original']} has changed since it was added (fingerprint mismatch)"

    capture = HERE / source["capture"]
    if not capture.exists():
        return "held", f"text file {source['capture']} is missing"
    if source.get("capture_sha256") and sha256_of(capture) != source["capture_sha256"]:
        return "held", f"{source['capture']} has changed since it was extracted (fingerprint mismatch)"

    quote = claim.get("quote", "")
    if not quote.strip():
        return "held", "claim has no quote"
    if normalize(quote) not in normalize(capture.read_text(encoding="utf-8")):
        return "held", "quote does not appear word for word in the source"

    wanted = to_number(claim.get("value", ""))
    if wanted is None:
        return "held", f"value '{claim.get('value')}' is not a number"
    if abs(wanted) not in numbers_in(quote):
        return "held", f"value {claim.get('value')} does not appear in the quote"

    return "verified", ""


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def run_checks():
    sources = {s["id"]: s for s in load(SOURCES)}
    claims = load(CLAIMS)
    rows = []
    for c in claims:
        status, reason = check_claim(c, sources)
        rows.append((c, status, reason))
    verified = sum(1 for _, s, _ in rows if s == "verified")

    lines = ["# Claim check report", "",
             f"{len(rows)} claims: {verified} verified, {len(rows) - verified} held.",
             "Generated by `python3 verify.py`. Do not edit by hand.", "",
             "| Claim | What | Value | Unit | Period | Source | Status | Reason |",
             "|---|---|---|---|---|---|---|---|"]
    for c, status, reason in rows:
        mark = "verified" if status == "verified" else "**held**"
        lines.append("| " + " | ".join(cell(x) for x in [
            c.get("claim_id", ""), c.get("subject", ""), c.get("value", ""),
            c.get("unit", ""), c.get("period", ""), c.get("source_id", ""),
            mark, reason]) + " |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} claims: {verified} verified, {len(rows) - verified} held. See REPORT.md.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        add_source(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "fetch":
        fetch_source(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "paste":
        paste_source(sys.argv[2:])
    else:
        run_checks()
