"""Assemble the simple yearly kickoff email without persisted templates."""

from collections.abc import Iterable, Mapping
from html import escape


def kickoff_recipients(rows: Iterable[Mapping[str, object]]) -> list[str]:
    """Return non-empty contact addresses once, preserving query order."""
    recipients = []
    for row in rows:
        address = row.get("email_address")
        if not isinstance(address, str) or not address.strip():
            raise ValueError("Kickoff rows require a contact email address")
        if address not in recipients:
            recipients.append(address)
    return recipients


def build_folder_links_section(rows: Iterable[Mapping[str, object]]) -> str:
    """Format active repository share links as one block per person."""
    people: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        name = row.get("full_name")
        repository = row.get("repository_name")
        share_url = row.get("share_url")
        if not all(isinstance(value, str) and value.strip() for value in (name, repository, share_url)):
            raise ValueError("Folder-link rows require a name, repository, and share URL")
        links = people.setdefault(name, [])
        link = (repository, share_url)
        if link not in links:
            links.append(link)

    lines = []
    for name, links in people.items():
        links_text = " | ".join(
            f"{repository}: {share_url}" for repository, share_url in links
        )
        lines.append(f"{name} — {links_text}")
    return "\n".join(lines)


def build_folder_links_html(rows: Iterable[Mapping[str, object]]) -> str:
    """Format share links as compact, safely escaped HTML rows."""
    people: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        name = row.get("full_name")
        repository = row.get("repository_name")
        share_url = row.get("share_url")
        if not all(isinstance(value, str) and value.strip() for value in (name, repository, share_url)):
            raise ValueError("Folder-link rows require a name, repository, and share URL")
        link = (repository, share_url)
        links = people.setdefault(name, [])
        if link not in links:
            links.append(link)

    lines = []
    for name, links in people.items():
        links_html = " | ".join(
            f'<a href="{escape(url, quote=True)}">{escape(repository)}</a>'
            for repository, url in links
        )
        lines.append(f"{escape(name)} — {links_html}")
    return "<br>\n".join(lines)


def assemble_kickoff_body(
    main_text: str,
    folder_rows: Iterable[Mapping[str, object]],
    signature: str,
    *,
    closing_text: str | None = None,
) -> str:
    """Append the generated folder section and explicit signature to freeform text."""
    if not main_text.strip():
        raise ValueError("Kickoff main text must not be empty")
    if not signature.strip():
        raise ValueError("Kickoff signature must not be empty")
    links = build_folder_links_section(folder_rows)
    if not links:
        raise ValueError("Kickoff email requires at least one active folder link")
    closing = f"\n\n{closing_text.strip()}" if closing_text and closing_text.strip() else ""
    return f"{main_text.strip()}\n\n{links}{closing}\n\n{signature.strip()}"


def assemble_kickoff_html(
    main_html: str,
    folder_rows: Iterable[Mapping[str, object]],
    signature_html: str,
    *,
    closing_html: str | None = None,
) -> str:
    """Append linked folder rows and a formatted signature to supplied HTML."""
    if not main_html.strip():
        raise ValueError("Kickoff main HTML must not be empty")
    if not signature_html.strip():
        raise ValueError("Kickoff signature HTML must not be empty")
    links = build_folder_links_html(folder_rows)
    if not links:
        raise ValueError("Kickoff email requires at least one active folder link")
    closing = closing_html.strip() if closing_html and closing_html.strip() else ""
    return f"{main_html.strip()}<p>{links}</p>{closing}{signature_html.strip()}"
