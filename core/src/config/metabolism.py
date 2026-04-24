from pydantic import BaseModel

class MetabolismSettings(BaseModel):
    # Holonom v3.0 Parameters
    pcrit: float = 0.2857  # 2/7
    sad_max: int = 3
    kappa_boot: float = 5.71
    sigma_k_max: float = 0.95

    # Hill Regulator Parameters
    hill_n: float = 2.8

    # Initial Coherence State
    # We need initial purity P = trace(Gamma^2) > pcrit (0.2857)
    # [0.6, 0.1, 0.06, 0.06, 0.06, 0.06, 0.06] => 0.36 + 0.01 + 5*0.0036 = 0.388 > 0.2857
    initial_diagonal: list[float] = [0.6, 0.1, 0.06, 0.06, 0.06, 0.06, 0.06]
