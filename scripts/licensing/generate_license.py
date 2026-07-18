#!/usr/bin/env python3
"""FlipRadar — generator de chei de licenta Ed25519 (KEY-1). Unealta lui David.

Subcomenzi:
  gen-keys                        genereaza perechea Ed25519 (o singura data)
  issue --lid ID [--name] [--exp] emite o cheie de activare semnata
  verify <cheie>                  valideaza o cheie cu cheia publica din service

Formatul cheii:  FLIP.<b64url(payload_json)>.<b64url(semnatura_64B)>  (fara padding)
Payload compact: {"lid","iss"[,"name"][,"exp"]}, semnat cu cheia privata Ed25519.

Cheia PRIVATA (scripts/licensing/keys/license_private.pem) e GITIGNORED si NU se
distribuie niciodata. Pierderea ei = imposibil de emis chei compatibile cu
build-urile deja livrate (publicul e hardcodat in license_service.py). FA BACKUP.
"""
import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KEYS_DIR = REPO / "scripts" / "licensing" / "keys"
PRIVATE_PEM = KEYS_DIR / "license_private.pem"


def _b64u(b: bytes) -> str:
    """base64url fara padding (acelasi format ca segmentele cheii)."""
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _load_private():
    from cryptography.hazmat.primitives import serialization
    if not PRIVATE_PEM.is_file():
        sys.exit(f"[license] cheia privata lipseste: {PRIVATE_PEM}\n"
                 f"          ruleaza intai `gen-keys`.")
    return serialization.load_pem_private_key(PRIVATE_PEM.read_bytes(), password=None)


def cmd_gen_keys(_args):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    if PRIVATE_PEM.exists():
        sys.exit(f"[license] REFUZ suprascrierea: {PRIVATE_PEM} exista deja.\n"
                 f"          Sterge-l manual DOAR daca esti sigur — pierderea cheii "
                 f"inseamna chei incompatibile cu build-urile deja livrate.")
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    PRIVATE_PEM.write_bytes(pem)
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    pub_b64 = _b64u(pub_raw)
    print(f"[license] cheie privata scrisa: {PRIVATE_PEM}")
    print("[license] gitignored — FA BACKUP; pierderea ei e ireversibila.")
    print()
    print("Pune aceasta cheie publica in backend/app/services/license_service.py:")
    print(f'    LICENSE_PUBLIC_KEY_B64 = "{pub_b64}"')
    print(f"    (base64url raw, {len(pub_b64)} caractere)")


def cmd_issue(args):
    priv = _load_private()
    payload = {"lid": args.lid, "iss": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    if args.name:
        payload["name"] = args.name
    if args.exp:
        try:
            datetime.strptime(args.exp, "%Y-%m-%d")
        except ValueError:
            sys.exit(f"[license] --exp invalid (astept YYYY-MM-DD): {args.exp}")
        payload["exp"] = args.exp
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = priv.sign(payload_bytes)
    print("FLIP." + _b64u(payload_bytes) + "." + _b64u(sig))


def cmd_verify(args):
    # Pattern-ul scripturilor de diagnostic: backend/ pe sys.path, apoi import service.
    sys.path.insert(0, str(REPO / "backend"))
    try:
        from app.services.license_service import parse_license, LicenseError
    except Exception as e:  # pragma: no cover — mediu incomplet
        sys.exit(f"[license] nu pot importa license_service: {e}")
    try:
        payload = parse_license(args.key)
    except LicenseError as e:
        sys.exit(f"[license] INVALID: {e}")
    print("[license] VALID. Payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(
        description="FlipRadar — generator chei de licenta Ed25519 (KEY-1).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen-keys", help="genereaza perechea Ed25519 (o singura data)")
    p_issue = sub.add_parser("issue", help="emite o cheie de activare semnata")
    p_issue.add_argument("--lid", required=True, help="ID licenta, ex: FR-0001")
    p_issue.add_argument("--name", help="nume client (optional)")
    p_issue.add_argument("--exp", help="data expirarii YYYY-MM-DD (optional)")
    p_verify = sub.add_parser("verify", help="valideaza o cheie emisa")
    p_verify.add_argument("key", help="cheia de activare FLIP.<...>.<...>")
    args = ap.parse_args()
    {"gen-keys": cmd_gen_keys, "issue": cmd_issue, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    main()
