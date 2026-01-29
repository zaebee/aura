from pydantic import BaseModel

class LogicSettings(BaseModel):
    min_margin: float = 0.10  # 10% minimum margin
