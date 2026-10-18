"""Native callback configuration contracts; no SDK or provider calls."""
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]


def test_ios_google_client_callback_preserves_provider_callback_and_client_types():
    info = plistlib.loads((ROOT / "apps/specimen_digitization/ios/Runner/Info.plist").read_bytes())
    client = info["GIDClientID"]
    server = info["GIDServerClientID"]
    assert client == "716045864126-6m846krhsfsucmkmpkte88ra6kirv12a.apps.googleusercontent.com"
    assert server == "716045864126-9g71pv45aeqimivdl8de5m7tm4ilk6gj.apps.googleusercontent.com"
    schemes = [scheme for entry in info["CFBundleURLTypes"] for scheme in entry["CFBundleURLSchemes"]]
    assert schemes == ["specimenintake", ".".join(reversed(client.split(".")))]
