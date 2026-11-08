"""Sign in with CAFECA — backend verification (no CAFECA server takes part; we read the chain ourselves).

Follows CAFECA's integration guide (docs/integration.md, app/src/lib/signin.ts):
1. the response is `type: "cafeca:auth"`, `v: 1`, with a well-formed `account` (the identity contract);
2. `message.domain` equals our origin exactly, `message.nonce` is one we issued to this browser (single use,
   consumed before the signature check), `chainId` matches, `issuedAt ≤ now + 60 ≤ expiresAt + 60`;
3. `hash = EIP-712(domain = {CAFECA Sign-In, 1, chainId, verifyingContract: account}, SignIn, message)`;
4. `account.isValidSignature(hash, signature)` via `eth_call` must return the ERC-1271 magic value 0x1626ba7e;
5. if `kyc_level` was approved, `identityRegistry.statusOf(account)` → `effectiveLevel` when status is ACTIVE.

The account address — never the handle — is the viewer's id. Configuration comes from
`<wallet>/.well-known/cafeca-configuration` (cached), overridable under `site.cafeca` in config.yaml.
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from ..config import settings
from ..log import get_logger

log = get_logger("site.cafeca")

try:  # keccak-256 (not NIST SHA3)
    from Crypto.Hash import keccak as _keccak

    def keccak(b: bytes) -> bytes:
        return _keccak.new(digest_bits=256, data=b).digest()
except ImportError:  # pragma: no cover
    try:
        from eth_hash.auto import keccak as _ek  # type: ignore

        def keccak(b: bytes) -> bytes:
            return _ek(b)
    except ImportError:
        def keccak(b: bytes) -> bytes:
            raise RuntimeError("keccak-256 needs pycryptodome (pip install pycryptodome)")

MAGIC_1271 = "1626ba7e"
SIGNIN_TYPE = ("SignIn(string domain,string uri,string nonce,uint256 issuedAt,uint256 expiresAt,"
               "string statement,string claims,string channel)")
DOMAIN_TYPE = "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
CLAIMS = ("kyc_level", "handle", "legal_name", "doc_type", "nationality", "pairwise_id", "entity_ubn", "entity_name")
ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
HANDLE = re.compile(r"^[a-z0-9_]{3,20}$")
STATUS = ("none", "active", "suspended", "revoked")
SIGNER = ("none", "prototype", "production")


class SignInError(ValueError):
    pass


def wallet() -> str:
    return str(settings().get("site.cafeca.wallet", "https://cafeca.io")).rstrip("/")


_cfg: tuple[float, dict] | None = None


def configuration() -> dict:
    """`.well-known/cafeca-configuration`, cached for an hour; values in config.yaml win."""
    global _cfg
    override = settings().get("site.cafeca", {}) or {}
    if _cfg and time.time() - _cfg[0] < 3600:
        base = _cfg[1]
    else:
        try:
            base = httpx.get(wallet() + "/.well-known/cafeca-configuration", timeout=10).json()
            _cfg = (time.time(), base)
        except Exception as e:  # noqa: BLE001
            if not _cfg:
                raise SignInError(f"無法讀取 CAFECA 設定：{e}") from e
            base = _cfg[1]
    chain = dict(base.get("chain") or {})
    if override.get("chain_id"):
        chain["id"] = int(override["chain_id"])
    if override.get("rpc"):
        chain["rpc"] = override["rpc"]
    contracts = dict(base.get("contracts") or {})
    contracts.update(override.get("contracts") or {})
    return {"chain": chain, "contracts": contracts, "sdk": base.get("sdk") or wallet() + "/sdk/cafeca-connect.js"}


# ---------------------------------------------------------------------------------------- EIP-712
def _word_uint(n: int) -> bytes:
    return int(n).to_bytes(32, "big")


def _word_addr(a: str) -> bytes:
    return bytes(12) + bytes.fromhex(a[2:])


def _str(s: str) -> bytes:
    return keccak((s or "").encode("utf-8"))


def normalize_claims(claims: Any) -> str:
    if isinstance(claims, str):
        claims = [c for c in claims.split(",") if c]
    return ",".join(sorted({c for c in (claims or []) if c in CLAIMS}))


def signin_hash(message: dict, chain_id: int, account: str) -> bytes:
    domain_sep = keccak(keccak(DOMAIN_TYPE.encode()) + _str("CAFECA Sign-In") + _str("1") + _word_uint(chain_id)
                        + _word_addr(account))
    struct = keccak(keccak(SIGNIN_TYPE.encode()) + _str(message["domain"]) + _str(message["uri"]) + _str(message["nonce"])
                    + _word_uint(int(message["issuedAt"])) + _word_uint(int(message["expiresAt"]))
                    + _str(message.get("statement") or "") + _str(normalize_claims(message.get("claims")))
                    + _str(message.get("channel") or ""))
    return keccak(b"\x19\x01" + domain_sep + struct)


# ---------------------------------------------------------------------------------------- chain reads
def _selector(sig: str) -> str:
    return keccak(sig.encode()).hex()[:8]


def _abi_bytes32_bytes(h: bytes, sig: bytes) -> str:
    pad = (32 - len(sig) % 32) % 32
    return (h.hex() + _word_uint(64).hex() + _word_uint(len(sig)).hex() + sig.hex() + "00" * pad)


def eth_call(rpc: str, to: str, data: str, timeout: float = 10) -> str:
    r = httpx.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                              "params": [{"to": to, "data": "0x" + data}, "latest"]}, timeout=timeout)
    j = r.json()
    if j.get("error"):
        raise SignInError(f"鏈上查詢失敗：{j['error'].get('message', j['error'])}")
    return (j.get("result") or "0x")[2:]


def is_valid_signature(rpc: str, account: str, h: bytes, signature: str) -> bool:
    sig = bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)
    try:
        out = eth_call(rpc, account, _selector("isValidSignature(bytes32,bytes)") + _abi_bytes32_bytes(h, sig))
    except Exception as e:  # noqa: BLE001
        log.warning("isValidSignature call failed: %s", e)
        return False
    return out[:8].lower() == MAGIC_1271


def identity_status(rpc: str, registry: str, account: str) -> dict:
    out = eth_call(rpc, registry, _selector("statusOf(address)") + _word_addr(account).hex())
    w = [int(out[i:i + 64] or "0", 16) for i in range(0, min(len(out), 64 * 11), 64)]
    if len(w) < 10:
        return {"status": "none", "effectiveLevel": 0, "signerClass": "none"}
    return {"subjectType": "entity" if w[0] == 1 else "person", "level": w[1], "effectiveLevel": w[2],
            "status": STATUS[w[3]] if w[3] < len(STATUS) else "none",
            "signerClass": SIGNER[w[9]] if w[9] < len(SIGNER) else "none"}


def lookup_handle(account: str) -> str | None:
    try:
        h = httpx.get(wallet() + "/api/profile", params={"q": account}, timeout=8).json().get("handle")
        return h if isinstance(h, str) and HANDLE.match(h) else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------------------- verify
def verify(res: dict, *, origin: str, nonce_ok, now: float | None = None) -> dict:
    """Return {account, handle, kyc_level, claims}. `nonce_ok(nonce) -> bool` consumes the nonce (single use)."""
    now = now or time.time()
    if not isinstance(res, dict) or res.get("type") != "cafeca:auth" or int(res.get("v", 1)) != 1:
        raise SignInError("不是 CAFECA 登入回應")
    if res.get("error"):
        raise SignInError("使用者取消登入" if res["error"] == "access_denied" else str(res["error"]))
    account = str(res.get("account") or "")
    if not ADDR.match(account):
        raise SignInError("帳戶地址錯誤")
    m = res.get("message") or {}
    for k in ("domain", "uri", "nonce", "issuedAt", "expiresAt"):
        if k not in m:
            raise SignInError(f"登入訊息缺少 {k}")
    if m["domain"] != origin:
        raise SignInError("登入訊息的網域不符（可能來自仿冒網站）")
    if not nonce_ok(str(m["nonce"])):                       # invalidated before verification
        raise SignInError("nonce 不符或已使用")
    cfg = configuration()
    chain_id = int(cfg["chain"]["id"])
    if int(res.get("chainId", -1)) != chain_id:
        raise SignInError("鏈 ID 不符")
    if now > int(m["expiresAt"]):
        raise SignInError("登入已過期")
    if int(m["issuedAt"]) > now + 60:
        raise SignInError("登入時間不合理")
    if not is_valid_signature(cfg["chain"]["rpc"], account, signin_hash(m, chain_id, account), str(res.get("signature") or "")):
        raise SignInError("簽章驗證失敗")
    approved = set(normalize_claims(m.get("claims")).split(",")) - {""}
    kyc = None
    if "kyc_level" in approved and cfg["contracts"].get("identityRegistry"):
        try:
            st = identity_status(cfg["chain"]["rpc"], cfg["contracts"]["identityRegistry"], account)
            kyc = int(st["effectiveLevel"]) if st["status"] == "active" else 0
        except Exception as e:  # noqa: BLE001
            log.warning("statusOf failed for %s: %s", account, e)
    handle = None
    if "handle" in approved:
        handle = lookup_handle(account)
    return {"account": account.lower(), "handle": handle, "kyc_level": kyc, "claims": sorted(approved)}
