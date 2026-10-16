"""Keep repository URLs out of public copy while preserving attribution text."""
import re


# Includes subdomains, raw assets and Pages; also catches protocol-relative URLs.
GITHUB_URL = re.compile(
    r'(?:(?:https?:)?//|\bwww\.)'
    r'(?:[a-z0-9-]+\.)*(?:github\.com|githubusercontent\.com|githubassets\.com|github\.io)'
    r'(?=[:/\s<>"\x27)\]}.,!?;]|$)(?::\d+)?'
    r'(?:[/#?][^\s<>"\x27)\]]*)?',
    re.IGNORECASE,
)


def release_notes(text):
    """Keep Markdown link labels and replace bare repository URLs with references.

    Notes are rendered as escaped plain text, so no Markdown/HTML is activated.
    Sanitise before writing either HTML or the public release manifest.
    """
    text = re.sub(
        r'!?\[([^\]\n]*)\]\(\s*<?(' + GITHUB_URL.pattern + r')>?'
        r'(?:\s+["\x27][^\n]*?["\x27])?\s*\)',
        lambda match: match[1], text, flags=re.IGNORECASE,
    )
    return GITHUB_URL.sub('[project reference]', text)
