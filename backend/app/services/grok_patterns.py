"""Grok pattern service for parsing log files with named capture groups.

Grok patterns allow defining reusable regex components that can be
referenced by name. For example, %{IP:client_ip} would capture an
IP address into a field named "client_ip".

Built-in patterns are always available. Users can add custom patterns
through the API, which are stored in the database.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.database import get_grok_patterns_dict


# Built-in grok patterns (based on common Logstash/Elastic patterns)
BUILTIN_GROK_PATTERNS: dict[str, str] = {
    # Basic patterns
    "WORD": r"\b\w+\b",
    "NOTSPACE": r"\S+",
    "SPACE": r"\s*",
    "DATA": r".*?",
    "GREEDYDATA": r".*",
    "QUOTEDSTRING": r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'',

    # Numbers
    "INT": r"(?:[+-]?(?:[0-9]+))",
    "NUMBER": r"(?:[+-]?(?:(?:[0-9]+(?:\.[0-9]+)?)|(?:\.[0-9]+)))",
    "POSINT": r"\b(?:[1-9][0-9]*)\b",
    "NONNEGINT": r"\b(?:[0-9]+)\b",
    "BASE10NUM": r"(?:[+-]?(?:(?:[0-9]+(?:\.[0-9]+)?)|(?:\.[0-9]+)))",
    "BASE16NUM": r"(?:0[xX])?[0-9A-Fa-f]+",
    "BASE16FLOAT": r"\b(?:[+-]?(?:0x)?(?:[0-9A-Fa-f]+(?:\.[0-9A-Fa-f]*)?|\.[0-9A-Fa-f]+))\b",

    # Network
    "IP": r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)",
    "IPV4": r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)",
    "IPV6": r"(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){1,7}:|(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){1,5}(?::[0-9A-Fa-f]{1,4}){1,2}|(?:[0-9A-Fa-f]{1,4}:){1,4}(?::[0-9A-Fa-f]{1,4}){1,3}|(?:[0-9A-Fa-f]{1,4}:){1,3}(?::[0-9A-Fa-f]{1,4}){1,4}|(?:[0-9A-Fa-f]{1,4}:){1,2}(?::[0-9A-Fa-f]{1,4}){1,5}|[0-9A-Fa-f]{1,4}:(?::[0-9A-Fa-f]{1,4}){1,6}|:(?::[0-9A-Fa-f]{1,4}){1,7}|::)",
    "IPORHOST": r"(?:%{IP}|%{HOSTNAME})",
    "HOSTNAME": r"\b(?:[0-9A-Za-z][0-9A-Za-z-]{0,62})(?:\.(?:[0-9A-Za-z][0-9A-Za-z-]{0,62}))*(?:\.?|\b)",
    "HOST": r"%{HOSTNAME}",
    "HOSTPORT": r"%{IPORHOST}:%{POSINT}",
    "PORT": r"\b(?:[0-9]{1,5})\b",
    "MAC": r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}",

    # Paths
    "PATH": r"(?:/[^\s]*|[A-Za-z]:\\[^\s]*)",
    "UNIXPATH": r"(?:/[^\s]*)+",
    "WINPATH": r"(?:[A-Za-z]:\\[^\s]*)+",
    "URI": r"%{URIPROTO}://(?:%{USER}(?::[^@]*)?@)?(?:%{URIHOST})?(?:%{URIPATHPARAM})?",
    "URIPROTO": r"[A-Za-z][A-Za-z0-9+.-]*",
    "URIHOST": r"%{IPORHOST}(?::%{POSINT})?",
    "URIPATH": r"(?:/[^\s?#]*)*",
    "URIPARAM": r"\?[^\s#]*",
    "URIPATHPARAM": r"%{URIPATH}(?:%{URIPARAM})?",

    # Date/Time
    "MONTH": r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b",
    "MONTHNUM": r"(?:0?[1-9]|1[0-2])",
    "MONTHDAY": r"(?:0?[1-9]|[12][0-9]|3[01])",
    "DAY": r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)",
    "YEAR": r"(?:[0-9]{2}){1,2}",
    "HOUR": r"(?:2[0123]|[01]?[0-9])",
    "MINUTE": r"(?:[0-5][0-9])",
    "SECOND": r"(?:(?:[0-5]?[0-9]|60)(?:[:.,][0-9]+)?)",
    "TIME": r"(?:%{HOUR}:%{MINUTE}:%{SECOND})",
    "DATE_US": r"%{MONTHNUM}[/-]%{MONTHDAY}[/-]%{YEAR}",
    "DATE_EU": r"%{MONTHDAY}[./-]%{MONTHNUM}[./-]%{YEAR}",
    "ISO8601_TIMEZONE": r"(?:Z|[+-]%{HOUR}(?::?%{MINUTE})?)",
    "ISO8601_SECOND": r"(?:%{SECOND}|60)",
    "TIMESTAMP_ISO8601": r"%{YEAR}-%{MONTHNUM}-%{MONTHDAY}[T ]%{HOUR}:?%{MINUTE}(?::?%{SECOND})?%{ISO8601_TIMEZONE}?",
    "DATE": r"%{DATE_US}|%{DATE_EU}",
    "DATESTAMP": r"%{DATE}[- ]%{TIME}",
    "TZ": r"(?:[PMCE][SD]T|UTC)",
    "DATESTAMP_RFC822": r"%{DAY} %{MONTH} %{MONTHDAY} %{YEAR} %{TIME} %{TZ}",
    "DATESTAMP_RFC2822": r"%{DAY}, %{MONTHDAY} %{MONTH} %{YEAR} %{TIME} %{ISO8601_TIMEZONE}",
    "DATESTAMP_OTHER": r"%{DAY} %{MONTH} %{MONTHDAY} %{TIME} %{TZ} %{YEAR}",
    "DATESTAMP_EVENTLOG": r"%{YEAR}%{MONTHNUM}%{MONTHDAY}%{HOUR}%{MINUTE}%{SECOND}",

    # Syslog
    "SYSLOGTIMESTAMP": r"%{MONTH} +%{MONTHDAY} %{TIME}",
    "SYSLOGPROG": r"%{DATA:program}(?:\\[%{POSINT:pid}\\])?",
    "SYSLOGHOST": r"%{IPORHOST}",
    "SYSLOGFACILITY": r"<%{NONNEGINT:facility}.%{NONNEGINT:priority}>",
    "SYSLOG5424PRI": r"<%{NONNEGINT:syslog5424_pri}>",

    # HTTP
    "HTTPDATE": r"%{MONTHDAY}/%{MONTH}/%{YEAR}:%{TIME} %{INT}",
    "HTTPVERSION": r"HTTP/(?:1\\.0|1\\.1|2(?:\\.0)?)",

    # Log levels
    "LOGLEVEL": r"(?:TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERR(?:OR)?|CRIT(?:ICAL)?|FATAL|SEVERE|EMERG(?:ENCY)?)",

    # User/Auth
    "USER": r"[a-zA-Z0-9._-]+",
    "USERNAME": r"[a-zA-Z0-9._-]+",
    "EMAILADDRESS": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}",

    # UUIDs
    "UUID": r"[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}",
}


def get_all_patterns() -> dict[str, str]:
    """Get all available grok patterns (built-in + custom from database).

    Custom patterns from the database override built-in patterns with the same name.
    """
    patterns = BUILTIN_GROK_PATTERNS.copy()

    # Load custom patterns from database (these override built-ins)
    custom_patterns = get_grok_patterns_dict()
    patterns.update(custom_patterns)

    return patterns


def expand_grok(pattern: str, max_depth: int = 10) -> str:
    """Expand grok pattern references (%{PATTERN} or %{PATTERN:name}) to regex.

    Args:
        pattern: Grok pattern string with %{...} references
        max_depth: Maximum recursion depth for nested patterns

    Returns:
        Expanded regex pattern string

    Raises:
        ValueError: If pattern reference is unknown or max depth exceeded
    """
    if max_depth <= 0:
        raise ValueError("Maximum pattern expansion depth exceeded (circular reference?)")

    all_patterns = get_all_patterns()

    # Pattern to match %{NAME} or %{NAME:field_name} or %{NAME:field_name:type}
    grok_ref = re.compile(r'%\{([A-Z0-9_]+)(?::([a-zA-Z0-9_]+))?(?::[a-z]+)?\}')

    def replace_pattern(match: re.Match) -> str:
        pattern_name = match.group(1)
        field_name = match.group(2)

        if pattern_name not in all_patterns:
            raise ValueError(f"Unknown grok pattern: {pattern_name}")

        replacement = all_patterns[pattern_name]

        # Recursively expand nested patterns
        if '%{' in replacement:
            replacement = expand_grok(replacement, max_depth - 1)

        # If field name specified, wrap in named capture group
        if field_name:
            return f"(?P<{field_name}>{replacement})"
        else:
            # Non-capturing group
            return f"(?:{replacement})"

    return grok_ref.sub(replace_pattern, pattern)


def parse_with_grok(text: str, pattern: str) -> dict[str, Any] | None:
    """Parse text using a grok pattern and return captured fields.

    Args:
        text: Text to parse
        pattern: Grok pattern with %{PATTERN:field} syntax

    Returns:
        Dictionary of captured field names to values, or None if no match
    """
    try:
        regex = expand_grok(pattern)
        match = re.match(regex, text)

        if match:
            return match.groupdict()
        return None
    except (ValueError, re.error):
        return None


def validate_grok_pattern(pattern: str) -> tuple[bool, str | None]:
    """Validate a grok pattern string.

    Args:
        pattern: Grok pattern to validate

    Returns:
        (is_valid, error_message) - True if valid, or False with error message
    """
    try:
        regex = expand_grok(pattern)
        re.compile(regex)
        return True, None
    except ValueError as e:
        return False, str(e)
    except re.error as e:
        return False, f"Invalid regex: {e}"


def validate_regex_pattern(regex: str) -> tuple[bool, str | None]:
    """Validate a raw regex pattern string.

    Args:
        regex: Regex pattern to validate

    Returns:
        (is_valid, error_message) - True if valid, or False with error message
    """
    try:
        re.compile(regex)
        return True, None
    except re.error as e:
        return False, f"Invalid regex: {e}"


def list_builtin_patterns() -> list[dict[str, str]]:
    """Get list of built-in grok patterns for display in UI.

    Returns:
        List of dicts with 'name', 'regex', and 'description' keys
    """
    # Descriptions for built-in patterns
    descriptions = {
        "WORD": "A single word (alphanumeric + underscore)",
        "NOTSPACE": "Any non-whitespace characters",
        "SPACE": "Zero or more whitespace characters",
        "DATA": "Non-greedy match of any characters",
        "GREEDYDATA": "Greedy match of any characters",
        "QUOTEDSTRING": "Single or double quoted string",
        "INT": "Integer with optional sign",
        "NUMBER": "Decimal number with optional sign",
        "POSINT": "Positive integer",
        "NONNEGINT": "Non-negative integer",
        "IP": "IPv4 address",
        "IPV4": "IPv4 address",
        "IPV6": "IPv6 address",
        "HOSTNAME": "Hostname (DNS name)",
        "HOSTPORT": "Host and port (e.g., example.com:8080)",
        "PORT": "Port number (1-65535)",
        "MAC": "MAC address",
        "PATH": "File system path (Unix or Windows)",
        "UNIXPATH": "Unix file system path",
        "WINPATH": "Windows file system path",
        "URI": "Full URI with protocol",
        "URIPROTO": "URI protocol/scheme",
        "URIPATH": "URI path component",
        "MONTH": "Month name (Jan, January, etc.)",
        "MONTHNUM": "Month number (01-12)",
        "MONTHDAY": "Day of month (01-31)",
        "DAY": "Day name (Mon, Monday, etc.)",
        "YEAR": "2 or 4 digit year",
        "HOUR": "Hour (00-23)",
        "MINUTE": "Minute (00-59)",
        "SECOND": "Second (00-60, with optional decimal)",
        "TIME": "Time in HH:MM:SS format",
        "DATE_US": "US date format (MM/DD/YYYY)",
        "DATE_EU": "European date format (DD/MM/YYYY)",
        "TIMESTAMP_ISO8601": "ISO 8601 timestamp",
        "DATESTAMP": "Date and time combined",
        "SYSLOGTIMESTAMP": "Syslog timestamp format",
        "HTTPDATE": "HTTP/CLF date format",
        "HTTPVERSION": "HTTP version (1.0, 1.1, 2)",
        "LOGLEVEL": "Common log levels (DEBUG, INFO, WARN, ERROR, etc.)",
        "USER": "Username (alphanumeric, dot, underscore, hyphen)",
        "USERNAME": "Username (alphanumeric, dot, underscore, hyphen)",
        "EMAILADDRESS": "Email address",
        "UUID": "UUID/GUID",
    }

    result = []
    for name, regex in sorted(BUILTIN_GROK_PATTERNS.items()):
        result.append({
            "name": name,
            "regex": regex,
            "description": descriptions.get(name, ""),
            "builtin": True,
        })

    return result
