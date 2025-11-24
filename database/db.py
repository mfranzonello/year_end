from sqlalchemy import create_engine, text, Engine
from pandas import read_sql_query, DataFrame

def get_engine(host:str, port:str, dbname:str, user:str, password:str):
    engine = create_engine(f'postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}')
    return engine

def build_values(df: DataFrame, cols:list[str]) -> tuple[str, dict[str, object]]:
    # get values and params for complex calls
    value_clauses = []
    params: dict[str, object] = {}

    for idx, row in df[cols].iterrows():
        append_string = ', '.join(f':{c}_{idx}' for c in cols)
        value_clauses.append(f'({append_string})')
        for c in cols:
            params[f'{c}_{idx}'] = row[f'{c}']
        
    values = ', '.join(value_clauses)

    return values, params

def read_sql(engine:Engine, sql:str) -> DataFrame:
    with engine.begin() as conn:
        df = read_sql_query(text(sql), conn)

    return df

def execute_sql(engine:Engine, sql:str, params:dict|None=None,
                df:DataFrame|None=None, returning:bool=False):
    if isinstance(params, dict):
        with engine.begin() as conn:
            result = conn.execute(text(sql), params or {})

    elif isinstance(df, DataFrame):
        if not df.empty:
            rows = df.to_dict(orient="records")
            with engine.begin() as conn:
                result = conn.execute(text(sql), rows)
        else:
            result = None

    else:
        with engine.begin() as conn:
            result = conn.execute(text(sql))

    if returning and result:
        return result.fetchall()