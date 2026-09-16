from flag import flag as region_flag

def get_flag(region_code: str) -> str:
    if region_code:
        return region_flag(region_code)