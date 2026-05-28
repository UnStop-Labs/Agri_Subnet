"""
Test a complete commit+reveal cycle as fast as possible.
Run: python test_commit_reveal.py

This confirms whether the issue is timing (window too narrow)
or something else (call format, permissions, etc.)
"""
import hashlib, os, struct, sys, time

WS_URL  = os.getenv("SUBTENSOR_ADDRESS", "ws://127.0.0.1:9945")
NETUID  = int(os.getenv("NETUID", "2"))
WALLET  = os.getenv("WALLET_NAME", "test-validator")
HOTKEY  = os.getenv("HOTKEY_NAME", "default")
VERSION_KEY = int(os.getenv("VERSION_KEY", "1000"))

try:
    from substrateinterface import SubstrateInterface
    from fiber.chain import chain_utils
except ImportError as e:
    sys.exit(f"Import error: {e}")

substrate = SubstrateInterface(url=WS_URL)
keypair   = chain_utils.load_hotkey_keypair(WALLET, HOTKEY)

# ── SCALE helpers ──────────────────────────────────────────────────
def su16(v):  return struct.pack("<H", v & 0xFFFF)
def compact(n):
    if n < 64:      return bytes([n << 2])
    elif n < 16384: return struct.pack("<H", (n << 2) | 1)
    else:           return struct.pack("<I", (n << 2) | 2)
def vec_u16(vals): return compact(len(vals)) + b"".join(su16(v) for v in vals)
def su64(v):  return struct.pack("<Q", v)

def commit_hash(netuid, uids, values, salt, vk):
    data = su16(netuid) + vec_u16(uids) + vec_u16(values) + vec_u16(salt) + su64(vk)
    return "0x" + hashlib.blake2b(data, digest_size=32).hexdigest()

def current_block():
    return substrate.get_block()["header"]["number"]

# ── Test data ──────────────────────────────────────────────────────
uids   = [0, 1, 2]
values = [21845, 21845, 21845]  # equal weights
salt   = [int.from_bytes(os.urandom(2), "little") for _ in range(len(uids))]  # must match len(uids)
chash  = commit_hash(NETUID, uids, values, salt, VERSION_KEY)

print(f"\n{'='*60}")
print(f"Test: commit_weights then reveal_weights on netuid {NETUID}")
print(f"  uids   = {uids}")
print(f"  values = {values}")
print(f"  salt   = {salt}")
print(f"  hash   = {chash}")
print(f"  block  = {current_block()}")
print(f"{'='*60}\n")

# ── STEP 1: commit ─────────────────────────────────────────────────
print(">>> STEP 1: commit_weights")
t0 = time.time()
call = substrate.compose_call("SubtensorModule", "commit_weights",
    {"netuid": NETUID, "commit_hash": chash})
extrinsic = substrate.create_signed_extrinsic(call=call, keypair=keypair)
try:
    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    if not receipt.is_success:
        sys.exit(f"commit_weights FAILED dispatch: {receipt.error_message}")
    print(f"    commit OK in {time.time()-t0:.2f}s, block={current_block()}")
except Exception as exc:
    sys.exit(f"commit_weights EXCEPTION: {exc}")

# ── STEP 2: read reveal window ─────────────────────────────────────
print(">>> STEP 2: read WeightCommits")
stored = substrate.query("SubtensorModule", "WeightCommits",
    [NETUID, keypair.ss58_address]).value
print(f"    stored = {stored}")
entry = stored[0]
_, commit_block_num, first_reveal, last_reveal = entry
print(f"    commit_block={commit_block_num}  first_reveal={first_reveal}  last_reveal={last_reveal}")
print(f"    window_width={last_reveal - first_reveal} blocks")
print(f"    current_block={current_block()}")

# ── STEP 3: wait until PAST first_reveal ───────────────────────────
print(f">>> STEP 3: waiting for block > {first_reveal}  (currently at {current_block()})")
t_wait = time.time()
while True:
    cb = current_block()
    if cb > first_reveal:
        print(f"    block={cb}  elapsed={time.time()-t_wait:.2f}s — inside window, revealing NOW")
        break
    time.sleep(0.05)

# ── STEP 4: reveal ─────────────────────────────────────────────────
cb_now = current_block()
print(f">>> STEP 4: reveal_weights at block {cb_now}  (window [{first_reveal},{last_reveal}])")
if cb_now > last_reveal:
    print(f"    *** WINDOW EXPIRED before reveal! cb={cb_now} > last={last_reveal}")
    sys.exit("Window expired — the window is too narrow for this chain speed")

t1 = time.time()
reveal_call = substrate.compose_call("SubtensorModule", "reveal_weights", {
    "netuid":      NETUID,
    "uids":        uids,
    "values":      values,
    "salt":        salt,
    "version_key": VERSION_KEY,
})
extrinsic = substrate.create_signed_extrinsic(call=reveal_call, keypair=keypair)
try:
    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    if receipt.is_success:
        print(f"\n*** reveal_weights SUCCEEDED in {time.time()-t1:.2f}s ***")
    else:
        print(f"\n*** reveal_weights dispatch FAILED: {receipt.error_message}")
except Exception as exc:
    print(f"\n*** reveal_weights POOL REJECTED: {exc}")
    print(f"    block at rejection: {current_block()}")
    print(f"    reveal window was:  [{first_reveal}, {last_reveal}]")
    print(f"    were we in window?  {first_reveal < current_block() <= last_reveal}")

print(f"\nDone. Final block: {current_block()}")
