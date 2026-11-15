"""Zombie API Necropolis backend."""

__version__ = "0.1.0"
REPO_URL = "https://github.com/TrendCatcher2/necropolis"

# safety.md rules 4 and 6: one descriptive User-Agent for the archive client and for probes. Never personal data.
USER_AGENT = f"Necropolis/{__version__} (+{REPO_URL}; owner-verified scan)"
