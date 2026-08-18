"""Build a concise phone-selection sheet from manually approved vCard matches."""

import argparse
import csv
import json
import re
from pathlib import Path


TYPE_PRIORITY = {
    "iphone": 0,
    "cell": 1,
    "mobile": 1,
    "home": 2,
    "other": 3,
    "work": 4,
    "main": 5,
    "unspecified": 6,
}


def phone_type(parameters: str) -> str:
    """Return the most useful vCard telephone type for review ordering."""
    types = [
        value.casefold()
        for value in re.findall(r"type=([^;:,]+)", parameters, flags=re.IGNORECASE)
    ]
    useful = [value for value in types if value not in {"voice", "pref"}]
    return min(useful, key=lambda value: TYPE_PRIORITY.get(value, 5), default="unspecified")


def _phone_options(extracted: dict[str, str]) -> list[dict[str, str]]:
    raw_phones = json.loads(extracted["raw_phones"])
    normalized_phones = json.loads(extracted["normalized_phones"])
    normalized_by_digits = {
        "".join(character for character in value if character.isdigit()): value
        for value in normalized_phones
    }
    options: dict[str, dict[str, str]] = {}
    for parameters, raw_number in raw_phones:
        digits = "".join(character for character in raw_number if character.isdigit())
        normalized = next(
            (
                value
                for normalized_digits, value in normalized_by_digits.items()
                if digits.endswith(normalized_digits[-10:])
            ),
            "",
        )
        key = normalized or digits or raw_number
        label = phone_type(parameters)
        current = options.get(key)
        if current is None or TYPE_PRIORITY.get(label, 5) < TYPE_PRIORITY.get(current["type"], 5):
            options[key] = {
                "type": label,
                "raw": raw_number,
                "normalized": normalized,
            }
    return sorted(
        options.values(),
        key=lambda option: (TYPE_PRIORITY.get(option["type"], 5), option["normalized"], option["raw"]),
    )


def build_selected_phone_review(
    candidates_path: Path,
    extracted_path: Path,
    output_path: Path,
) -> dict[str, int]:
    """Join TRUE person matches to their phones and write a compact review sheet."""
    with candidates_path.open(encoding="utf-8-sig", newline="") as source:
        selected = [
            row
            for row in csv.DictReader(source)
            if (row.get("match") or "").strip().upper() == "TRUE"
        ]
    with extracted_path.open(encoding="utf-8-sig", newline="") as source:
        extracted = {row["vcard_index"]: row for row in csv.DictReader(source)}

    vcard_counts: dict[str, int] = {}
    person_counts: dict[str, int] = {}
    for row in selected:
        vcard_counts[row["vcard_index"]] = vcard_counts.get(row["vcard_index"], 0) + 1
        person_counts[row["person_id"]] = person_counts.get(row["person_id"], 0) + 1
    if any(count != 1 for count in vcard_counts.values()):
        raise ValueError("TRUE selections must contain each vCard at most once")
    if any(count != 1 for count in person_counts.values()):
        raise ValueError("TRUE selections must contain each person at most once")

    output_rows = []
    maximum_phones = 0
    for match in selected:
        source = extracted.get(match["vcard_index"])
        if source is None:
            raise ValueError(f"Missing extracted vCard {match['vcard_index']}")
        options = _phone_options(source)
        maximum_phones = max(maximum_phones, len(options))
        output_row: dict[str, object] = {
            "vcard_index": match["vcard_index"],
            "person_id": match["person_id"],
            "database_name": match["database_name"],
            "vcard_name": match["formatted_name"],
            "phone_count": len(options),
            "selection_status": "default_single" if len(options) == 1 else "needs_review",
            "selected_phone_number": options[0]["normalized"] or options[0]["raw"]
            if len(options) == 1
            else "",
            "review_notes": "",
        }
        for index, option in enumerate(options, start=1):
            output_row[f"phone_{index}_type"] = option["type"]
            output_row[f"phone_{index}_raw"] = option["raw"]
            output_row[f"phone_{index}_normalized"] = option["normalized"]
        output_rows.append(output_row)

    fixed_fields = [
        "vcard_index", "person_id", "database_name", "vcard_name", "phone_count",
    ]
    phone_fields = [
        f"phone_{index}_{field}"
        for index in range(1, maximum_phones + 1)
        for field in ("type", "raw", "normalized")
    ]
    final_fields = ["selection_status", "selected_phone_number", "review_notes"]
    output_rows.sort(key=lambda row: str(row["database_name"]).casefold())
    with output_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fixed_fields + phone_fields + final_fields)
        writer.writeheader()
        writer.writerows(output_rows)

    return {
        "selected_matches": len(output_rows),
        "default_single": sum(row["selection_status"] == "default_single" for row in output_rows),
        "needs_review": sum(row["selection_status"] == "needs_review" for row in output_rows),
        "maximum_phones": maximum_phones,
    }


def main() -> None:
    """Create a private phone-selection CSV from reviewed match artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_selected_phone_review(args.candidates, args.extracted, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
