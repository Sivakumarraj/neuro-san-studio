"""List the URLs upstream CI's lychee link check will request for the given files."""

import re
import sys
from pathlib import Path

URL_PATTERN: re.Pattern[str] = re.compile(r"https?://[^\s\"'`)<>\]]+")
EXAMPLE_DOMAINS: tuple[str, ...] = ("example.com", "example.org", "example.net")
IGNORE_FILE: Path = Path(".lycheeignore")


class LinkCheck:
    """
    Applies `.lycheeignore` and lychee's example-domain rule offline, so the URLs CI would request
    can be reviewed before a push. It does not fetch anything: CI remains the check of record.
    """

    @staticmethod
    def main() -> None:
        """
        Print every URL in the files named on the command line that CI would still check.
        """
        patterns: list[re.Pattern[str]] = LinkCheck._patterns()
        remaining: set[str] = set()
        for name in sys.argv[1:]:
            path: Path = Path(name)
            files: list[Path] = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
            for file in files:
                for url in URL_PATTERN.findall(file.read_text(encoding="utf-8", errors="ignore")):
                    url = url.rstrip(".,;:")
                    if not LinkCheck._excluded(url, patterns):
                        remaining.add(url)
        for url in sorted(remaining):
            print(url)

    @staticmethod
    def _patterns() -> list[re.Pattern[str]]:
        """
        :return: The `.lycheeignore` entries as regular expressions, comments and blanks dropped.
        """
        lines: list[str] = IGNORE_FILE.read_text(encoding="utf-8").splitlines()
        return [re.compile(line.strip()) for line in lines if line.strip() and not line.startswith("#")]

    @staticmethod
    def _excluded(url: str, patterns: list[re.Pattern[str]]) -> bool:
        """
        :param url: A URL found in a file.
        :param patterns: The ignore patterns.
        :return: True when lychee would skip it: an example domain, or a match against an ignore
            pattern in the URL as written or with braces in its path percent-encoded, as lychee
            reports them.
        """
        host: str = re.sub(r"^https?://", "", url).split("/")[0].split("?")[0]
        if host in EXAMPLE_DOMAINS or host.endswith(tuple(f".{domain}" for domain in EXAMPLE_DOMAINS)):
            return True
        match: re.Match[str] | None = re.match(r"(https?://[^/?#]+)([^?#]*)(.*)", url)
        encoded: str = url
        if match:
            encoded = match.group(1) + match.group(2).replace("{", "%7B").replace("}", "%7D") + match.group(3)
        return any(pattern.search(url) or pattern.search(encoded) for pattern in patterns)


if __name__ == "__main__":
    LinkCheck.main()
