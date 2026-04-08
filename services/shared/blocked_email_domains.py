"""
Domains that indicate personal (non-work) email addresses.
Users must provide a work email to access free tools.
"""

BLOCKED_DOMAINS = frozenset({
    # Major free email providers
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.ca", "yahoo.com.au",
    "ymail.com", "rocketmail.com",
    "outlook.com", "hotmail.com", "hotmail.co.uk", "live.com", "msn.com",
    "aol.com",
    "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "pm.me",
    "zoho.com", "zohomail.com",
    "mail.com",
    "gmx.com", "gmx.net", "gmx.de",
    "yandex.com", "yandex.ru",
    "tutanota.com", "tuta.io",
    "fastmail.com", "fastmail.fm",
    "hushmail.com",
    "mailfence.com",
    "disroot.org",
    "posteo.de", "posteo.net",
    "runbox.com",
    "startmail.com",
    "cock.li",
    # Temporary / disposable email services
    "tempmail.com", "temp-mail.org", "guerrillamail.com", "guerrillamail.net",
    "sharklasers.com", "grr.la", "guerrillamailblock.com",
    "mailinator.com", "maildrop.cc", "dispostable.com",
    "throwaway.email", "trashmail.com", "trashmail.net",
    "10minutemail.com", "minutemail.com",
    "yopmail.com", "yopmail.fr",
    "getnada.com", "nada.email",
    "mailnesia.com", "mailcatch.com",
    "tempail.com", "tempr.email",
    # ISP consumer email
    "comcast.net", "verizon.net", "att.net", "sbcglobal.net",
    "charter.net", "cox.net", "earthlink.net",
    "bellsouth.net", "windstream.net", "centurylink.net",
    # Regional consumer email
    "qq.com", "163.com", "126.com", "yeah.net",
    "sina.com", "sohu.com", "aliyun.com",
    "naver.com", "daum.net", "hanmail.net",
    "web.de", "freenet.de", "t-online.de",
    "libero.it", "virgilio.it",
    "laposte.net", "orange.fr", "wanadoo.fr",
    "rediffmail.com",
    "mail.ru", "inbox.ru", "list.ru", "bk.ru",
})


def is_personal_email(email: str) -> bool:
    """Check if an email address uses a personal/free email domain."""
    try:
        domain = email.strip().lower().split("@")[1]
        return domain in BLOCKED_DOMAINS
    except (IndexError, AttributeError):
        return True  # Malformed email = reject


def extract_domain(email: str) -> str:
    """Extract the domain from an email address."""
    try:
        return email.strip().lower().split("@")[1]
    except (IndexError, AttributeError):
        raise ValueError(f"Invalid email format: {email}")
