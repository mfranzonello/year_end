"""Assemble the simple yearly kickoff email without persisted templates."""

from collections.abc import Iterable, Mapping


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

    blocks = []
    for name, links in people.items():
        lines = [f"{name}:"]
        lines.extend(f"{repository}: {share_url}" for repository, share_url in links)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def assemble_kickoff_body(
    main_text: str,
    folder_rows: Iterable[Mapping[str, object]],
    signature: str,
) -> str:
    """Append the generated folder section and explicit signature to freeform text."""
    if not main_text.strip():
        raise ValueError("Kickoff main text must not be empty")
    if not signature.strip():
        raise ValueError("Kickoff signature must not be empty")
    links = build_folder_links_section(folder_rows)
    if not links:
        raise ValueError("Kickoff email requires at least one active folder link")
    return f"{main_text.strip()}\n\n{links}\n\n{signature.strip()}"
