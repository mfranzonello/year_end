import argparse
from datetime import datetime

from family_tree.statistics import get_summaries

def main():
    ap = argparse.ArgumentParser(description=f"Print folder summaries.")
   
    YEAR = datetime.now().year
    ap.add_argument("--year", type=int, default=YEAR, help=f"Year subfolder to process (default: {YEAR})")

    args = ap.parse_args()
    
    values = get_summaries(args.year)

    print(values)

if __name__ == "__main__":
    main()
