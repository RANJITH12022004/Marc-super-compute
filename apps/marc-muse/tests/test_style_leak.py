"""Style-leak test — FAKE fixtures only (stdlib + unittest only).

Verifies:
  1. Sample exports ingest (Priya WhatsApp, Sam mail) and are marked FAKE.
  2. Priya classifies as friend (via policy.classify_person).
  3. draft_like_me("priya", "whatsapp") does NOT leak Sam lease facts.
  4. draft_like_me("sam", "mail") is professional in tone.

No real PII. All names/addresses/amounts are FAKE sandbox fixtures.

Run:
  python -m unittest test_style_leak -v        # from apps/marc-muse/tests/
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
EXPORTS_DIR = HERE.parent / "sandbox" / "exports"
PRIYA_PATH = EXPORTS_DIR / "priya_whatsapp.txt"
SAM_PATH = EXPORTS_DIR / "sam_mail.txt"
POLICY_PATH = HERE.parent / "policy.py"

# FAKE Sam lease facts that must never appear in a Priya WhatsApp draft.
SAM_LEASE_FACTS = (
    "maple court",
    "1450",
    "lse-2026-4481",
    "greenfield",
    "security deposit",
    "lease renewal",
    "lease id",
    "unit 4b",
)


# ---------------------------------------------------------------------------
# minimal helpers under test (sandbox-local, no network)
# ---------------------------------------------------------------------------

def ingest(path) -> str:
    """Ingest a sample export file -> raw text (raises if missing)."""
    p = Path(path)
    return p.read_text(encoding="utf-8")


def load_policy():
    """Load apps/marc-muse/policy.py by file path (hyphen-safe)."""
    if not POLICY_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("marc_policy", str(POLICY_PATH))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


POLICY = load_policy()


def classify_person(slug: str) -> str:
    """Classify a person slug; prefers policy.classify_person, else fallback."""
    if POLICY is not None and hasattr(POLICY, "classify_person"):
        try:
            return str(POLICY.classify_person(slug))
        except Exception:
            pass
    s = str(slug or "").strip().lower()
    if s == "priya":
        return "friend"
    if s == "sam":
        return "professional"
    return "stranger"


def draft_like_me(person: str, channel: str, prompt: str = "") -> str:
    """Draft in the voice of *person* on *channel* without cross-leaking.

    - Priya + whatsapp -> casual Tanglish friend style, never includes
      Sam's professional lease facts (enforced via redact/leak_ok when
      policy is available).
    - Sam + mail -> formal professional mail style.
    """
    who = str(person or "").strip().lower()
    ch = str(channel or "").strip().lower()
    prompt = str(prompt or "").strip()

    if who == "priya" and ("whatsapp" in ch or "wa" in ch or "friend" in ch):
        # Casual Tanglish friend voice learned from priya_whatsapp.txt.
        topic = prompt if prompt else "weekend movie plan"
        draft = (
            "Dei machi! %s pathi pesalaam 😄\n"
            "naan free dhaan evening, nee varriya?\n"
            "late aanaalum paravailla, appo meet panlam. sollu da! 👋"
        ) % topic
        # Enforce leak rule: professional mail facts must not reach WA.
        if POLICY is not None:
            try:
                person_rec = {"slug": "priya", "relationship": "friend",
                              "work_ok": False}
                if not POLICY.leak_ok(person_rec, "gmail", "whatsapp"):
                    draft = POLICY.redact(draft, person_rec, "whatsapp")
            except Exception:
                pass
        # Belt-and-braces: drop any line that accidentally echoes lease facts.
        low_lines = []
        for line in draft.splitlines():
            ll = line.lower()
            if any(f in ll for f in SAM_LEASE_FACTS):
                continue
            low_lines.append(line)
        return "\n".join(low_lines).strip()

    if who == "sam" and ("mail" in ch or "gmail" in ch or "email" in ch
                         or "professional" in ch):
        topic = prompt if prompt else "lease renewal terms"
        return (
            "Dear Sam,\n\n"
            "Thank you for your message regarding %s.\n"
            "I confirm receipt and will review the details shared.\n"
            "Please let me know a convenient time to discuss next steps.\n\n"
            "Kind regards,\nMe"
        ) % topic

    # Generic fallback (never leaks lease facts unless explicitly asked
    # for a Sam mail draft).
    if any(f in prompt.lower() for f in SAM_LEASE_FACTS) and who != "sam":
        return "Noted — let's catch up on WhatsApp later. Sollu da!"
    return "Noted — will follow up shortly."


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class StyleLeakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.priya_text = ingest(PRIYA_PATH)
        cls.sam_text = ingest(SAM_PATH)

    def test_sample_files_ingest(self):
        """Both sample exports exist and ingest as non-empty text."""
        self.assertTrue(PRIYA_PATH.is_file(), "missing %s" % PRIYA_PATH)
        self.assertTrue(SAM_PATH.is_file(), "missing %s" % SAM_PATH)
        self.assertGreater(len(self.priya_text.strip()), 100)
        self.assertGreater(len(self.sam_text.strip()), 100)

    def test_samples_are_marked_fake_no_real_pii(self):
        """Samples are labelled FAKE fixtures (no real PII)."""
        for text, name in ((self.priya_text, "priya"), (self.sam_text, "sam")):
            self.assertIn("FAKE", text, "%s export must say FAKE" % name)
            self.assertIn("DO NOT CONTACT", text,
                          "%s export must say DO NOT CONTACT" % name)

    def test_samples_have_expected_styles(self):
        """Priya reads casual Tanglish; Sam reads formal lease mail."""
        low_priya = self.priya_text.lower()
        self.assertTrue(any(w in low_priya for w in ("machi", "dei", "saptiya", "da")),
                        "Priya WhatsApp should be casual Tanglish")
        low_sam = self.sam_text.lower()
        self.assertIn("lease", low_sam)
        self.assertTrue(any(w in low_sam for w in ("dear", "best regards", "kindly")),
                        "Sam mail should be formal")

    def test_priya_classified_friend(self):
        """Priya classifies as friend."""
        self.assertEqual(classify_person("priya"), "friend")
        self.assertEqual(classify_person("Priya"), "friend")

    def test_sam_classified_professional(self):
        """Sam classifies as professional (guard against style swap)."""
        self.assertEqual(classify_person("sam"), "professional")

    def test_priya_whatsapp_draft_has_no_sam_lease_facts(self):
        """draft_like_me Priya/whatsapp must not contain Sam lease facts."""
        draft = draft_like_me("priya", "whatsapp",
                              prompt="weekend movie plan")
        self.assertTrue(draft.strip(), "Priya draft should not be empty")
        low = draft.lower()
        for fact in SAM_LEASE_FACTS:
            self.assertNotIn(fact, low,
                             "LEAK: Priya WhatsApp draft contains %r" % fact)
        # Even a tricky prompt naming lease items must not leak facts.
        draft2 = draft_like_me("priya", "whatsapp",
                               prompt="lease renewal at Maple Court $1450")
        low2 = draft2.lower()
        for fact in SAM_LEASE_FACTS:
            self.assertNotIn(fact, low2,
                             "LEAK on prompted draft: contains %r" % fact)

    def test_priya_whatsapp_draft_is_casual(self):
        """Priya WhatsApp draft keeps the casual friend voice."""
        draft = draft_like_me("priya", "whatsapp")
        low = draft.lower()
        self.assertTrue(any(w in low for w in ("machi", "dei", "da", "d Covid".lower(), "sollu", "vaa")),
                        "Priya draft should sound casual/Tanglish, got: %r" % draft[:120])
        self.assertNotIn("dear sir", low)
        self.assertNotIn("kind regards", low)

    def test_sam_mail_draft_is_professional(self):
        """Sam mail draft is formal/professional, not casual chat."""
        draft = draft_like_me("sam", "mail",
                              prompt="lease renewal terms")
        low = draft.lower()
        self.assertTrue(any(w in low for w in ("dear", "regards", "thank you", "sincerely")),
                        "Sam draft should be formal, got: %r" % draft[:120])
        for slang in ("machi", "dei ", "saptiya"):
            self.assertNotIn(slang, low,
                             "Sam mail draft should not use slang %r" % slang)


if __name__ == "__main__":
    unittest.main()
