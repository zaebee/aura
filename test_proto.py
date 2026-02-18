import betterproto
from aura_core_gen.aura.core.v1 import Signal

s = Signal()
try:
    print("Calling betterproto.which_one_of(s, 'payload')...")
    name, val = betterproto.which_one_of(s, "payload")
    print(f"Success: {name}")
except AttributeError as e:
    print(f"Failed: {e}")

try:
    print("Calling s.which_one_of('payload')...")
    name, val = s.which_one_of("payload")
    print(f"Success: {name}")
except AttributeError as e:
    print(f"Failed: {e}")
