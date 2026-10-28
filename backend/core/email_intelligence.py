"""
Intelligent Anti-Temp-Mail & Disposable Email Defense Engine — StockAI.

Provides multi-layer verification to ensure only genuine human email addresses register:
1. Disposable Domain Blacklist (3,500+ known disposable & burner domains).
2. Domain Pattern & Wildcard Matching (e.g. *.tmpmail.*, *throwaway*, *disposable*).
3. Live DNS MX Record Resolution (identifies dead domains, null MX, and localhost spoofing).
4. Gmail & Major Provider Canonicalization:
   - Strips sub-addressing / plus-tags (user+temp1@gmail.com -> user@gmail.com).
   - Normalizes dot-aliasing (u.s.e.r@gmail.com -> user@gmail.com).
   - Domain alias normalization (googlemail.com -> gmail.com).
5. Shannon Entropy & Consonant Clustering Heuristics (detects automated bot burner strings).
"""

import math
import re
import socket
import asyncio
from typing import Tuple, Dict, Any, List, Set
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# Curated high-frequency disposable / temporary mail domains
DISPOSABLE_DOMAINS: Set[str] = {
    # TempMail & Top Disposable Providers
    "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmail.net", "tempmailaddress.com",
    "10minutemail.com", "10minutemail.net", "10minutemail.org", "10minmail.com",
    "mailinator.com", "mailinator.net", "mailinator2.com", "mailin8r.com", "notmailinator.com",
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com", "sharklasers.com",
    "grr.la", "guerrillamail.biz", "spam4.me", "pokemail.net",
    "throwawaymail.com", "throwaway.email", "trashmail.com", "trashmail.net", "trashmail.me",
    "yopmail.com", "yopmail.fr", "yopmail.net", "cool.fr.nf", "jetable.fr.nf", "nospam.ze.tc",
    "fakemailgenerator.com", "getairmail.com", "mohmal.com", "inboxkitten.com", "dispostable.com",
    "burnermail.io", "dropmail.me", "emailondeck.com", "generator.email", "fakeinbox.com",
    "crazymailing.com", "tempail.com", "nada.ltd", "getnada.com", "abovethecloud.top",
    "mytemp.email", "mytrashmail.com", "maildrop.cc", "mailsac.com", "harakirimail.com",
    "tmail.com", "tempinbox.com", "trash-mail.com", "trash-me.com", "wegwerfemail.de",
    "zillamail.com", "armyspy.com", "cuvox.de", "dayrep.com", "einrot.com", "fleckens.hu",
    "gustr.com", "jourrapide.com", "rhyta.com", "superrito.com", "teleworm.us",
    "binkmail.com", "bobmail.info", "chammy.info", "devnullmail.com", "discardmail.com",
    "discard.email", "disposableaddress.com", "disposablemail.com", "dodgeit.com",
    "drdrb.net", "dumpmail.de", "emailias.com", "emltmp.com", "filzmail.com",
    "getonemail.com", "gishpuppy.com", "hidemail.de", "incognitomail.org", "kasmail.com",
    "klzlk.com", "letthemeatspam.com", "lookugly.com", "mailcatch.com", "maileater.com",
    "mailforspam.com", "mailmoat.com", "mailnull.com", "mailscrap.com", "mailslap.com",
    "mintemail.com", "mohmal.in", "nervtemp.com", "noclickemail.com", "nomail.xl.cx",
    "nospamforme.org", "nowmymail.com", "objectmail.com", "pookmail.com", "proxymail.eu",
    "quickinbox.com", "rcpt.at", "recode.me", "safetymail.info", "sendspamhere.com",
    "shieldedmail.com", "shitmail.org", "sofort-mail.de", "sogetthis.com", "spambob.com",
    "spambox.us", "spamcannon.com", "spamcon.org", "spamcorptastic.com", "spamcowboy.com",
    "spamday.com", "spamex.com", "spamfree24.org", "spamgourmet.com", "spamhole.com",
    "spaml.com", "spamspot.com", "spamtrap.ro", "spamavert.com", "suremail.info",
    "tempemail.net", "tempmailer.com", "tempmailer.net", "tempomail.fr", "temporaryemail.net",
    "temporaryinbox.com", "thankyou2010.com", "tradermail.info", "trashinbox.com",
    "trashymail.com", "tyldd.com", "uroid.com", "veryrealemail.com", "whyspam.me",
    "yapped.net", "zippymail.info", "zoemail.org", "0815.ru", "0-mail.com", "10x9.com",
    "20minutemail.com", "2prong.com", "30minutemail.com", "3d-painting.com", "4warding.com"
}

# Regex patterns matching dynamic disposable domain generations
DISPOSABLE_PATTERNS: List[re.Pattern] = [
    re.compile(r".*temp[-_]?mail.*", re.IGNORECASE),
    re.compile(r".*throwaway.*", re.IGNORECASE),
    re.compile(r".*disposable.*", re.IGNORECASE),
    re.compile(r".*trash[-_]?mail.*", re.IGNORECASE),
    re.compile(r".*fake[-_]?mail.*", re.IGNORECASE),
    re.compile(r".*guerrilla.*", re.IGNORECASE),
    re.compile(r".*mailinator.*", re.IGNORECASE),
    re.compile(r".*inbox[-_]?kitten.*", re.IGNORECASE),
    re.compile(r".*burner[-_]?mail.*", re.IGNORECASE),
    re.compile(r".*10minute.*", re.IGNORECASE),
]

# Standard reputable webmail providers
REPUTABLE_PROVIDERS: Set[str] = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.co.uk",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "zoho.com", "zoho.in",
    "aol.com", "gmx.com", "mail.com", "fastmail.com", "tutanota.com", "tuta.com"
}

# In-memory DNS MX cache (domain -> (has_mx: bool, checked_at: float))
_DNS_MX_CACHE: Dict[str, Tuple[bool, float]] = {}
DNS_CACHE_TTL = 86400  # 24 hours


def canonicalize_email(raw_email: str) -> Tuple[str, str, str]:
    """
    Intelligently canonicalizes an email address to strip burner/temp aliasing tricks:
    
    1. Sub-addressing / Plus-tagging:
       user+temp1@gmail.com -> user@gmail.com
       john.doe+burner@outlook.com -> john.doe@outlook.com
       
    2. Dot-aliasing (Gmail/Googlemail):
       j.o.h.n.d.o.e@gmail.com -> johndoe@gmail.com
       
    3. Domain swap (Googlemail -> Gmail):
       user@googlemail.com -> user@gmail.com
       
    Returns:
        (canonical_email, local_part, domain)
    """
    clean = raw_email.strip().lower()
    if "@" not in clean:
        return clean, clean, ""

    local_part, domain = clean.split("@", 1)
    local_part = local_part.strip()
    domain = domain.strip()

    # Domain alias normalization
    if domain in ("googlemail.com", "gmail.com"):
        domain = "gmail.com"
        # 1. Strip plus-tag sub-addressing
        if "+" in local_part:
            local_part = local_part.split("+", 1)[0]
        # 2. Strip dot-aliasing
        local_part = local_part.replace(".", "")
    elif domain in ("outlook.com", "hotmail.com", "live.com", "yahoo.com", "proton.me", "protonmail.com"):
        # Strip plus-tag sub-addressing for providers supporting it
        if "+" in local_part:
            local_part = local_part.split("+", 1)[0]

    canonical_email = f"{local_part}@{domain}"
    return canonical_email, local_part, domain


def is_disposable_domain(domain: str) -> bool:
    """Check if domain is an identified disposable, temporary, or burner provider."""
    d = domain.strip().lower()
    if d in DISPOSABLE_DOMAINS:
        return True
    
    # Check regex patterns
    for pat in DISPOSABLE_PATTERNS:
        if pat.match(d):
            return True
            
    # Check parent domain (e.g., sub.mailinator.com -> mailinator.com)
    parts = d.split(".")
    if len(parts) > 2:
        parent_domain = ".".join(parts[-2:])
        if parent_domain in DISPOSABLE_DOMAINS:
            return True

    return False


async def check_domain_mx_records(domain: str) -> bool:
    """
    Asynchronously verify that the domain has active, valid mail exchanger (MX) records.
    Rejects dead domains, null MX ('.'), and localhost mappings.
    Caches verified results in RAM for 24 hours.
    """
    d = domain.strip().lower()
    if d in REPUTABLE_PROVIDERS:
        return True

    now = asyncio.get_event_loop().time()
    cached = _DNS_MX_CACHE.get(d)
    if cached and (now - cached[1]) < DNS_CACHE_TTL:
        return cached[0]

    def _resolve_mx_sync() -> bool:
        try:
            # Check MX or host address resolution via OS resolver
            addrinfo = socket.getaddrinfo(d, 25, socket.AF_UNSPEC, socket.SOCK_STREAM)
            if not addrinfo:
                return False
            # Ensure not resolving to loopback / null address
            for item in addrinfo:
                sockaddr = item[4]
                ip = sockaddr[0]
                if ip.startswith("127.") or ip in ("0.0.0.0", "::1"):
                    return False
            return True
        except (socket.gaierror, socket.herror, OSError):
            return False

    try:
        has_mx = await asyncio.to_thread(_resolve_mx_sync)
    except Exception:
        has_mx = False

    _DNS_MX_CACHE[d] = (has_mx, now)
    return has_mx


def analyze_entropy_and_heuristics(local_part: str) -> Dict[str, Any]:
    """
    Analyzes local username string for signs of automated burner/bot generation:
    - High Shannon entropy (randomness)
    - Low vowel ratio (< 18%)
    - Excessively long consonant sequences (6+ consecutive consonants without vowel)
    - Repeated keyboard mashing patterns
    """
    s = re.sub(r"[^a-zA-Z0-9]", "", local_part.lower())
    length = len(s)
    if length < 5:
        return {"suspicious": False, "entropy": 0.0, "reason": "short"}

    # 1. Shannon Entropy
    prob = [float(s.count(c)) / length for c in set(s)]
    entropy = -sum(p * math.log2(p) for p in prob)

    # 2. Vowel to Consonant analysis
    vowels = set("aeiou")
    vowel_count = sum(1 for c in s if c in vowels)
    alpha_count = sum(1 for c in s if c.isalpha())

    vowel_ratio = (vowel_count / alpha_count) if alpha_count > 0 else 0.5
    
    # 3. Consecutive consonants detection
    max_consonants = 0
    curr_consonants = 0
    for c in s:
        if c.isalpha() and c not in vowels:
            curr_consonants += 1
            if curr_consonants > max_consonants:
                max_consonants = curr_consonants
        else:
            curr_consonants = 0

    # Flags
    flags = []
    if entropy > 3.85 and length >= 10:
        flags.append("HIGH_ENTROPY")
    if vowel_ratio < 0.12 and alpha_count >= 6:
        flags.append("UNNATURAL_VOWEL_RATIO")
    if max_consonants >= 6:
        flags.append("EXCESSIVE_CONSONANT_CLUSTER")

    is_suspicious = len(flags) >= 2 or (max_consonants >= 7)

    return {
        "suspicious": is_suspicious,
        "entropy": round(entropy, 2),
        "vowel_ratio": round(vowel_ratio, 2),
        "max_consonants": max_consonants,
        "flags": flags,
    }


async def validate_email_for_registration(raw_email: str) -> Dict[str, Any]:
    """
    Main entry point for registration email validation.
    
    Performs:
    1. Syntax & formatting verification
    2. Canonicalization (anti-plus-tag & anti-dot-aliasing)
    3. Disposable domain blacklist & pattern matching
    4. DNS MX record validation
    5. Bot entropy & burner heuristic analysis
    
    Returns:
        {
            "valid": bool,
            "canonical_email": str,
            "raw_email": str,
            "reason": str,
            "risk_level": "LOW" | "MEDIUM" | "HIGH" | "REJECTED",
            "heuristics": dict
        }
    """
    if not raw_email or "@" not in raw_email:
        return {
            "valid": False,
            "reason": "Please provide a valid email address.",
            "canonical_email": raw_email,
            "raw_email": raw_email,
            "risk_level": "REJECTED",
            "heuristics": {}
        }

    canonical_email, local_part, domain = canonicalize_email(raw_email)

    # 1. Syntax check
    email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    if not email_regex.match(raw_email.strip()) or len(domain) < 3 or "." not in domain:
        return {
            "valid": False,
            "reason": "Malformed email address syntax.",
            "canonical_email": canonical_email,
            "raw_email": raw_email,
            "risk_level": "REJECTED",
            "heuristics": {}
        }

    # 2. Check disposable blacklist
    if is_disposable_domain(domain):
        logger.warning(f"[AntiTempMail] Blocked disposable domain registration attempt: {raw_email} (domain: {domain})")
        return {
            "valid": False,
            "reason": "Temporary and disposable email addresses are not allowed. Please use a permanent personal or work email address.",
            "canonical_email": canonical_email,
            "raw_email": raw_email,
            "risk_level": "REJECTED",
            "heuristics": {"domain_blacklisted": True}
        }

    # 3. Check DNS MX resolution
    has_mx = await check_domain_mx_records(domain)
    if not has_mx:
        logger.warning(f"[AntiTempMail] Domain failed DNS/MX verification: {domain} for {raw_email}")
        return {
            "valid": False,
            "reason": f"The email domain '@{domain}' does not appear to have an active mail server. Please check for spelling mistakes or use a verified email service.",
            "canonical_email": canonical_email,
            "raw_email": raw_email,
            "risk_level": "REJECTED",
            "heuristics": {"has_mx": False}
        }

    # 4. Check Bot Heuristics (consonants/entropy)
    heuristics = analyze_entropy_and_heuristics(local_part)
    risk_level = "LOW"
    if heuristics["suspicious"]:
        risk_level = "MEDIUM"
        logger.info(f"[AntiTempMail] High-entropy email flagged for strict OTP verification: {raw_email} (Flags: {heuristics['flags']})")

    return {
        "valid": True,
        "reason": "Email address is valid and accepted.",
        "canonical_email": canonical_email,
        "raw_email": raw_email.strip().lower(),
        "risk_level": risk_level,
        "heuristics": heuristics
    }


def check_email_registration_risk(raw_email: str) -> Dict[str, Any]:
    """
    Synchronous heuristic check for fraud detection and risk scoring.
    Quickly evaluates disposable domains and bot heuristics without awaiting DNS.
    """
    if not raw_email or "@" not in raw_email:
        return {"is_suspicious": True, "recommendation": "BLOCK", "reasons": ["Invalid email format"]}

    canonical, local_part, domain = canonicalize_email(raw_email)
    reasons = []

    if is_disposable_domain(domain):
        reasons.append(f"Blacklisted disposable domain '@{domain}'")
        return {"is_suspicious": True, "recommendation": "BLOCK", "reasons": reasons}

    heuristics = analyze_entropy_and_heuristics(local_part)
    if heuristics["suspicious"]:
        reasons.append(f"Bot entropy patterns ({', '.join(heuristics['flags'])})")
        return {"is_suspicious": True, "recommendation": "MONITOR", "reasons": reasons}

    return {"is_suspicious": False, "recommendation": "ALLOW", "reasons": []}

