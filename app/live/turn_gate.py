"""
One cheap fast-path gate: obvious closing pleasantries ("thank you", "great to
hear") skip the LLM entirely, saving a call and keeping the rep's panel quiet.
All other intent understanding (question/opener/objection) is done by the LLM
itself inside the live prompt — no keyword lists.
"""

import re

_QUESTION_MARK = re.compile(r"\?")

_CLOSING_RE = re.compile(
    r"\b("
    r"thank(s| you)( so much| a lot)?|appreciate (it|you|that)|"
    r"great to hear|good to (hear|know)|sounds good|sounds great|"
    r"okay great|perfect|awesome|got it|alright then|"
    r"have a (good|great|nice) (day|evening|one)|talk (to you )?(later|soon)|"
    r"bye|goodbye"
    r")\b",
    re.IGNORECASE,
)

_QUESTION_STARTERS = frozenset(
    "what which where when why how who whose can could would should "
    "is are was were do does did will have has".split()
)


def looks_like_closing_or_acknowledgement(text: str) -> bool:
    """
    Pure pleasantry — "thank you", "great to hear this" — with no question and
    no new topic. Generating another pitch here makes the rep sound robotic;
    the turn should be skipped entirely.
    """
    t = (text or "").strip()
    words = t.split()
    if not words or len(words) > 8:
        return False
    if _QUESTION_MARK.search(t) or words[0].lower() in _QUESTION_STARTERS:
        return False
    return bool(_CLOSING_RE.search(t))
