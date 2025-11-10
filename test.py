import argparse
from datetime import datetime

from pandas import DataFrame

from family_tree.statistics import get_engine, fetch_folders, update_folders

def main():
    ap = argparse.ArgumentParser(description=f"Print folder summaries.")
   
    YEAR = datetime.now().year
    ap.add_argument("--year", type=int, default=YEAR, help=f"Year subfolder to process (default: {YEAR})")

    args = ap.parse_args()
    
    engine = get_engine()

    df = DataFrame([{'folder_name': 'Michael', 'project_year': 2025, 'video_count': 10, 'review_count': 20},
                    {'folder_name': 'Mobi', 'project_year': 2025, 'video_count': 4, 'review_count': 30}])
    update_folders(engine, df)
    values = fetch_folders(engine, args.year)

    print(values)

if __name__ == "__main__":
    main()
