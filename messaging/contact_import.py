"""Parse vCard exports and prepare conservative phone-import review files."""

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from sqlalchemy import Engine, text

from database.db import get_engine


@dataclass(frozen=True)
class VCardContact:
    """Contact fields needed for matching and phone review."""

    index: int
    formatted_name: str
    family_name: str
    given_name: str
    middle_names: str
    prefixes: str
    suffixes: str
    nicknames: tuple[str, ...]
    emails: tuple[str, ...]
    phones: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PersonCandidate:
    """Database person fields used to build name variants."""

    person_id: str
    first_name: str
    middle_names: str
    last_name: str
    married_name: str
    nick_name: str
    suffix: str
    email_address: str
    phone_number: str


def _unescape_vcard(value: str) -> str:
    """Decode vCard 3.0 text escapes without changing ordinary backslashes."""
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _unfold_lines(content: str) -> list[str]:
    """Join RFC 2425 continuation lines."""
    logical_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith((" ", "\t")) and logical_lines:
            logical_lines[-1] += line[1:]
        else:
            logical_lines.append(line)
    return logical_lines


def parse_vcards(path: Path) -> list[VCardContact]:
    """Parse the name, email, and telephone fields from a vCard 3.0 file."""
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    cards: list[VCardContact] = []
    current: dict[str, list[tuple[str, str]]] | None = None

    for line in _unfold_lines(content):
        if line.upper() == "BEGIN:VCARD":
            current = {}
            continue
        if line.upper() == "END:VCARD":
            if current is not None:
                cards.append(_build_vcard(len(cards) + 1, current))
            current = None
            continue
        if current is None or ":" not in line:
            continue

        raw_key, raw_value = line.split(":", 1)
        key_parts = raw_key.split(";")
        property_name = key_parts[0].split(".")[-1].upper()
        if property_name not in {"FN", "N", "NICKNAME", "EMAIL", "TEL"}:
            continue
        parameters = ";".join(key_parts[1:])
        current.setdefault(property_name, []).append(
            (parameters, _unescape_vcard(raw_value))
        )

    return cards


def _build_vcard(index: int, fields: dict[str, list[tuple[str, str]]]) -> VCardContact:
    n_value = fields.get("N", [("", "")])[0][1]
    n_parts = (n_value.split(";") + [""] * 5)[:5]
    family, given, middle, prefix, suffix = n_parts
    nicknames = tuple(
        item.strip()
        for _, value in fields.get("NICKNAME", [])
        for item in value.split(",")
        if item.strip()
    )
    emails = tuple(
        dict.fromkeys(
            value.strip().casefold()
            for _, value in fields.get("EMAIL", [])
            if value.strip()
        )
    )
    phones = tuple(
        dict.fromkeys(
            (parameters, value.strip())
            for parameters, value in fields.get("TEL", [])
            if value.strip()
        )
    )
    formatted_name = fields.get("FN", [("", "")])[0][1]
    return VCardContact(
        index=index,
        formatted_name=formatted_name,
        family_name=family,
        given_name=given,
        middle_names=middle,
        prefixes=prefix,
        suffixes=suffix,
        nicknames=nicknames,
        emails=emails,
        phones=phones,
    )


def normalize_name(value: str) -> str:
    """Return an accent- and punctuation-insensitive comparison name."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.casefold()))


def normalize_phone(value: str) -> str | None:
    """Normalize US numbers to the database's ten-digit text format."""
    main = re.split(r"(?:ext\.?|extension|x)\s*\d+\s*$", value, flags=re.IGNORECASE)[0]
    digits = "".join(re.findall(r"\d", main))
    if len(digits) == 10:
        return digits
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return None


def _person_variants(person: PersonCandidate) -> set[str]:
    surnames = {person.last_name, person.married_name} - {""}
    given_names = {person.first_name, person.nick_name} - {""}
    variants = {
        normalize_name(f"{given} {surname}")
        for given in given_names
        for surname in surnames
    }
    if person.middle_names:
        first_middle = person.middle_names.split(";", 1)[0]
        variants.update(
            normalize_name(f"{given} {first_middle} {surname}")
            for given in given_names
            for surname in surnames
        )
    if person.suffix:
        variants.update(
            normalize_name(f"{variant} {person.suffix}") for variant in tuple(variants)
        )
    return {variant for variant in variants if variant}


def _candidate_label(person: PersonCandidate) -> str:
    """Return a readable audit label without applying messaging name policy."""
    surname = person.married_name or person.last_name
    return " ".join(part for part in (person.first_name, surname, person.suffix) if part)


def _vcard_variants(card: VCardContact) -> set[str]:
    variants = {normalize_name(card.formatted_name)}
    surnames = {card.family_name} - {""}
    given_names = {card.given_name, *card.nicknames} - {""}
    variants.update(
        normalize_name(f"{given} {surname}")
        for given in given_names
        for surname in surnames
    )
    if card.middle_names:
        variants.update(
            normalize_name(f"{given} {card.middle_names} {surname}")
            for given in given_names
            for surname in surnames
        )
    return {variant for variant in variants if variant}


def _similarity(left_variants: set[str], right_variants: set[str]) -> float:
    if not left_variants or not right_variants:
        return 0.0
    return max(
        SequenceMatcher(None, left, right).ratio()
        for left in left_variants
        for right in right_variants
    )


def rank_candidates(
    card: VCardContact,
    people: Iterable[PersonCandidate],
) -> list[tuple[PersonCandidate, float, str]]:
    """Rank people using exact email, exact name variants, then fuzzy names."""
    card_emails = set(card.emails)
    card_names = _vcard_variants(card)
    ranked = []
    for person in people:
        person_names = _person_variants(person)
        if person.email_address and person.email_address.casefold() in card_emails:
            score, reason = 1.0, "exact_email"
        elif card_names & person_names:
            score, reason = 0.99, "exact_name"
        else:
            score = _similarity(card_names, person_names)
            reason = "fuzzy_name"
        if score >= 0.65:
            ranked.append((person, score, reason))
    return sorted(ranked, key=lambda item: (-item[1], item[0].person_id))


def fetch_people(engine: Engine) -> list[PersonCandidate]:
    """Fetch private matching components without relying on formatted-name views."""
    statement = text(
        """
        WITH married_names AS (
            SELECT marriages.wife_id, husbands.last_name AS married_name
            FROM marriages
            JOIN persons AS husbands ON husbands.person_id = marriages.husband_id
        )
        SELECT
            persons.person_id::text,
            COALESCE(persons.first_name, '') AS first_name,
            COALESCE(persons.middle_names, '') AS middle_names,
            COALESCE(persons.last_name, '') AS last_name,
            COALESCE(married_names.married_name, '') AS married_name,
            COALESCE(persons.nick_name, '') AS nick_name,
            COALESCE(suffix_to_text(persons.suffix), '') AS suffix,
            COALESCE(contacts.email_address, '') AS email_address,
            COALESCE(contacts.phone_number, '') AS phone_number
        FROM persons
        LEFT JOIN married_names ON married_names.wife_id = persons.person_id
        LEFT JOIN messaging.contacts AS contacts
          ON contacts.person_id = persons.person_id
        ORDER BY persons.person_id
        """
    )
    with engine.begin() as connection:
        rows = connection.execute(statement).mappings().all()
    return [PersonCandidate(**dict(row)) for row in rows]


def classify_match(
    ranked: list[tuple[PersonCandidate, float, str]],
) -> tuple[str, PersonCandidate | None, float, str]:
    """Classify one ranked result without automatically approving fuzzy matches."""
    if not ranked:
        return "unmatched", None, 0.0, "none"
    person, score, reason = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if reason == "exact_email" and second_score < 1.0:
        status = "strong_match"
    elif reason == "exact_name" and second_score < score:
        status = "strong_match"
    elif score >= 0.90 and score - second_score >= 0.08:
        status = "review_high"
    elif score >= 0.75:
        status = "review"
    else:
        status = "weak_or_unmatched"
    return status, person, score, reason


def write_review_files(
    cards: list[VCardContact],
    people: list[PersonCandidate],
    output_dir: Path,
) -> dict[str, object]:
    """Write extracted contacts and candidate matches under a private directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = output_dir / "vcf_contacts_extracted.csv"
    candidates_path = output_dir / "vcf_phone_match_candidates.csv"
    import_path = output_dir / "vcf_phone_import_review.csv"
    summary_path = output_dir / "vcf_phone_import_summary.json"
    counts: dict[str, object] = {"cards": len(cards), "cards_with_phone": 0}
    import_rows: list[dict[str, object]] = []

    with extracted_path.open("w", newline="", encoding="utf-8-sig") as extracted_file, \
         candidates_path.open("w", newline="", encoding="utf-8-sig") as candidate_file:
        extracted = csv.DictWriter(extracted_file, fieldnames=[
            "vcard_index", "formatted_name", "given_name", "middle_names",
            "family_name", "nicknames", "emails", "raw_phones", "normalized_phones",
        ])
        candidates = csv.DictWriter(candidate_file, fieldnames=[
            "vcard_index", "formatted_name", "candidate_rank", "person_id",
            "database_name", "score", "match_reason", "database_email",
            "current_phone_number",
        ])
        extracted.writeheader()
        candidates.writeheader()

        for card in cards:
            normalized_phones = tuple(
                dict.fromkeys(
                    normalized
                    for _, raw in card.phones
                    if (normalized := normalize_phone(raw)) is not None
                )
            )
            if card.phones:
                counts["cards_with_phone"] = int(counts["cards_with_phone"]) + 1
            extracted.writerow({
                "vcard_index": card.index,
                "formatted_name": card.formatted_name,
                "given_name": card.given_name,
                "middle_names": card.middle_names,
                "family_name": card.family_name,
                "nicknames": json.dumps(card.nicknames, ensure_ascii=False),
                "emails": json.dumps(card.emails, ensure_ascii=False),
                "raw_phones": json.dumps(card.phones, ensure_ascii=False),
                "normalized_phones": json.dumps(normalized_phones),
            })
            if not card.phones:
                continue

            ranked = rank_candidates(card, people)
            for rank, (person, score, reason) in enumerate(ranked[:3], start=1):
                candidates.writerow({
                    "vcard_index": card.index,
                    "formatted_name": card.formatted_name,
                    "candidate_rank": rank,
                    "person_id": person.person_id,
                    "database_name": _candidate_label(person),
                    "score": f"{score:.3f}",
                    "match_reason": reason,
                    "database_email": person.email_address,
                    "current_phone_number": person.phone_number,
                })

            status, person, score, reason = classify_match(ranked)
            counts[status] = int(counts.get(status, 0)) + 1
            if person is None:
                phone_action = "no_person_match"
                database_name = ""
                current_phone = ""
                person_id = ""
            else:
                current_normalized = normalize_phone(person.phone_number) if person.phone_number else None
                if not normalized_phones:
                    phone_action = "phone_needs_manual_normalization"
                elif current_normalized in normalized_phones:
                    phone_action = "already_current"
                elif person.phone_number:
                    phone_action = "conflicts_with_existing"
                elif len(normalized_phones) == 1:
                    phone_action = "candidate_new_phone"
                else:
                    phone_action = "multiple_phone_numbers"
                database_name = _candidate_label(person)
                current_phone = person.phone_number
                person_id = person.person_id
            if person is not None and status != "strong_match":
                phone_action = "review_person_match_first"
            import_rows.append({
                "vcard_index": card.index,
                "formatted_name": card.formatted_name,
                "match_status": status,
                "person_id": person_id,
                "database_name": database_name,
                "match_score": f"{score:.3f}",
                "match_reason": reason,
                "raw_phones": json.dumps(card.phones, ensure_ascii=False),
                "normalized_phones": json.dumps(normalized_phones),
                "current_phone_number": current_phone,
                "phone_action": phone_action,
                "approved": "",
            })

    person_counts = Counter(
        str(row["person_id"])
        for row in import_rows
        if row["person_id"] and row["match_status"] == "strong_match"
    )
    for row in import_rows:
        duplicate_count = person_counts.get(str(row["person_id"]), 0)
        row["strong_vcards_for_person"] = duplicate_count
        if duplicate_count > 1 and row["match_status"] == "strong_match":
            row["phone_action"] = "multiple_vcards_for_person"

    import_fields = [
        "vcard_index", "formatted_name", "match_status", "person_id",
        "database_name", "match_score", "match_reason", "raw_phones",
        "normalized_phones", "current_phone_number", "strong_vcards_for_person",
        "phone_action", "approved",
    ]
    with import_path.open("w", newline="", encoding="utf-8-sig") as import_file:
        imports = csv.DictWriter(import_file, fieldnames=import_fields)
        imports.writeheader()
        imports.writerows(import_rows)

    counts["phone_actions"] = dict(Counter(str(row["phone_action"]) for row in import_rows))
    counts["strong_people_with_multiple_vcards"] = sum(
        1 for duplicate_count in person_counts.values() if duplicate_count > 1
    )

    summary_path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


def build_engine() -> Engine:
    """Build the configured PostgreSQL engine."""
    from common.secret import secrets

    config = secrets["postgresql"]
    return get_engine(
        config["host"],
        config.get("port", "5432"),
        config["database"],
        config["user"],
        config["password"],
    )


def main() -> None:
    """Parse a private VCF export and create review artifacts without DB writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vcf_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("input"))
    args = parser.parse_args()
    cards = parse_vcards(args.vcf_path)
    people = fetch_people(build_engine())
    counts = write_review_files(cards, people, args.output_dir)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
