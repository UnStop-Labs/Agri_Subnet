"""
Run on the server to diagnose the reveal_weights Custom error: 16.

Usage:
    cd /root/agri-subnet-internal-merge
    python diagnose_weights.py
"""
import hashlib
import os
import struct
import sys

WS_URL  = os.getenv("SUBTENSOR_ADDRESS", "ws://127.0.0.1:9945")
NETUID  = int(os.getenv("NETUID", "2"))
WALLET  = os.getenv("WALLET_NAME", "test-validator")
HOTKEY  = os.getenv("HOTKEY_NAME", "default")

try:
    from substrateinterface import SubstrateInterface
    from fiber.chain import chain_utils
except ImportError as e:
    sys.exit(f"Import error: {e}  — run inside the validator venv")

print(f"\n{'='*60}")
print(f"Connecting to {WS_URL}  netuid={NETUID}")
print(f"{'='*60}\n")

substrate = SubstrateInterface(url=WS_URL)

# ------------------------------------------------------------------
# 1. Dump the SubtensorModule Error enum so we know what 16 means
# ------------------------------------------------------------------
print("SubtensorModule Error enum:")
for pallet in substrate.get_metadata().pallets:
    if pallet.name == "SubtensorModule":
        for idx, err in enumerate(pallet.errors or []):
            marker = " <--- THIS IS Custom error: 16" if idx == 16 else ""
            print(f"  [{idx:3d}]  {err.name}{marker}")
        break
else:
    print("  SubtensorModule pallet NOT found in metadata!")

# ------------------------------------------------------------------
# 2. Check commit-reveal chain settings for the netuid
# ------------------------------------------------------------------
print(f"\nCommit-reveal settings for netuid {NETUID}:")
for storage_key in ("CommitRevealWeightsEnabled", "CommitRevealWeightsInterval"):
    try:
        val = substrate.query("SubtensorModule", storage_key, [NETUID]).value
        print(f"  {storage_key} = {val}")
    except Exception as exc:
        print(f"  {storage_key} = ERROR ({exc})")

# ------------------------------------------------------------------
# 3. Load the validator keypair and check WeightCommits storage
# ------------------------------------------------------------------
print(f"\nValidator keypair ({WALLET}/{HOTKEY}):")
try:
    keypair = chain_utils.load_hotkey_keypair(WALLET, HOTKEY)
    print(f"  ss58  = {keypair.ss58_address}")
    print(f"  pubkey = {keypair.public_key.hex() if hasattr(keypair.public_key, 'hex') else keypair.public_key[:8].hex() + '...'}")
except Exception as exc:
    print(f"  ERROR loading keypair: {exc}")
    keypair = None

if keypair:
    print(f"\nWeightCommits[{NETUID}, {keypair.ss58_address}]:")
    try:
        result = substrate.query(
            "SubtensorModule", "WeightCommits",
            [NETUID, keypair.ss58_address]
        )
        print(f"  stored value = {result.value}")
        if result.value:
            stored_hash, stored_block = result.value
            print(f"  commit_hash  = {stored_hash}")
            print(f"  commit_block = {stored_block}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

# ------------------------------------------------------------------
# 4. Reproduce the hash with and without hotkey to show which
#    format matches what the chain stores.
# ------------------------------------------------------------------
def scale_u16(v):
    return struct.pack("<H", v & 0xFFFF)

def scale_compact(n):
    if n < 64:        return bytes([n << 2])
    elif n < 16384:   return struct.pack("<H", (n << 2) | 1)
    else:             return struct.pack("<I", (n << 2) | 2)

def scale_vec_u16(vals):
    return scale_compact(len(vals)) + b"".join(scale_u16(v) for v in vals)

def scale_u64(v):
    return struct.pack("<Q", v)

# Example data (matches a real run — edit if needed)
test_uids    = [0, 1, 2]
test_values  = [18043, 18043, 29448]
test_salt    = [54787, 45540, 55024, 49784, 40461, 54119, 14840, 57528]
version_key  = int(os.getenv("VERSION_KEY", "1000"))

def hash_without_hotkey(netuid, uids, values, salt, vk):
    data = scale_u16(netuid) + scale_vec_u16(uids) + scale_vec_u16(values) + scale_vec_u16(salt) + scale_u64(vk)
    return "0x" + hashlib.blake2b(data, digest_size=32).hexdigest()

def hash_with_hotkey(hotkey_bytes, netuid, uids, values, salt, vk):
    data = bytes(hotkey_bytes) + scale_u16(netuid) + scale_vec_u16(uids) + scale_vec_u16(values) + scale_vec_u16(salt) + scale_u64(vk)
    return "0x" + hashlib.blake2b(data, digest_size=32).hexdigest()

if keypair:
    print(f"\nHash comparison (using test data uids={test_uids} salt starts with {test_salt[0]}):")
    h_no  = hash_without_hotkey(NETUID, test_uids, test_values, test_salt, version_key)
    h_yes = hash_with_hotkey(keypair.public_key, NETUID, test_uids, test_values, test_salt, version_key)
    print(f"  WITHOUT hotkey: {h_no}")
    print(f"  WITH    hotkey: {h_yes}")
    print()
    print("  → If the stored commit_hash above matches one of these, that's the correct format.")

print(f"\n{'='*60}\n")
