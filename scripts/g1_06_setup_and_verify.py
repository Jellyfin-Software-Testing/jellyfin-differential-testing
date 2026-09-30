#!/usr/bin/env python3
"""Prepare and verify the equivalent G1-06 state of two Jellyfin versions.

The runner is deliberately idempotent after a successful first run. It does not
delete an existing server configuration: removing a Jellyfin config is destructive
and should be an explicit operator decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "dataset-manifest.json"
DEFAULT_SEED_DIR = ROOT / "data" / "seed-data"
DEFAULT_REPORT = ROOT / "docs" / "evidence" / "G1-06-initial-state-parity.json"
CLIENT_AUTHORIZATION = (
    'MediaBrowser Client="Jellyfin Differential Testing", '
    'Device="G1-06 Seeder", DeviceId="g1-06-seeder", Version="1.0.0"'
)


class SetupError(RuntimeError):
    """An actionable setup or parity failure."""


@dataclass(frozen=True)
class Server:
    label: str
    base_url: str


class JellyfinClient:
    def __init__(self, server: Server, timeout: float) -> None:
        self.server = server
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-Emby-Authorization": CLIENT_AUTHORIZATION})
        self.token: str | None = None
        self.user_id: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        authenticate: bool = False,
        expected: Iterable[int] = (200, 204),
    ) -> requests.Response:
        headers: dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if authenticate:
            if not self.token:
                raise SetupError(f"{self.server.label}: no access token is available")
            headers["X-Emby-Token"] = self.token
            # Send the client identity explicitly on elevated endpoints. Jellyfin
            # 10.8 accepts the token for read requests but can challenge a write
            # request when the client identity is inherited only from the session.
            headers["X-Emby-Authorization"] = CLIENT_AUTHORIZATION
        response = self.session.request(
            method,
            f"{self.server.base_url}{path}",
            headers=headers,
            json=payload,
            params=params,
            timeout=self.timeout,
        )
        if response.status_code not in set(expected):
            body = response.text.replace("\n", " ")[:500]
            raise SetupError(
                f"{self.server.label}: {method} {path} returned "
                f"HTTP {response.status_code}: {body}"
            )
        return response

    def json(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any] | list[Any]:
        response = self.request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise SetupError(
                f"{self.server.label}: {method} {path} did not return JSON"
            ) from exc

    def wait_until_healthy(self, deadline: float) -> None:
        last_error = "not attempted"
        while time.monotonic() < deadline:
            try:
                response = self.session.get(
                    f"{self.server.base_url}/health", timeout=min(self.timeout, 5)
                )
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(2)
        raise SetupError(f"{self.server.label}: health check timed out ({last_error})")

    def startup_configuration_is_available(self) -> bool:
        response = self.session.get(
            f"{self.server.base_url}/Startup/Configuration", timeout=self.timeout
        )
        if response.status_code == 200:
            return True
        if response.status_code in (401, 404):
            return False
        raise SetupError(
            f"{self.server.label}: GET /Startup/Configuration returned "
            f"HTTP {response.status_code}: {response.text[:300]}"
        )

    def complete_startup(self, manifest: dict[str, Any], username: str, password: str) -> None:
        startup = manifest["startup"]
        remote_access = manifest["remoteAccess"]
        self.request(
            "POST",
            "/Startup/Configuration",
            payload={
                "UICulture": startup["uiCulture"],
                "MetadataCountryCode": startup["metadataCountryCode"],
                "PreferredMetadataLanguage": startup["preferredMetadataLanguage"],
            },
        )
        # Jellyfin 10.8 initializes its placeholder administrator lazily when
        # this endpoint is read. POST /Startup/User is an update, not a create.
        self.json("GET", "/Startup/User", expected=(200,))
        self.request(
            "POST",
            "/Startup/User",
            payload={"Name": username, "Password": password},
        )
        self.request(
            "POST",
            "/Startup/RemoteAccess",
            payload={
                "EnableRemoteAccess": remote_access["enableRemoteAccess"],
                "EnableAutomaticPortMapping": remote_access[
                    "enableAutomaticPortMapping"
                ],
            },
        )
        self.request("POST", "/Startup/Complete")

    def authenticate(self, username: str, password: str) -> None:
        response = self.request(
            "POST",
            "/Users/AuthenticateByName",
            payload={"Username": username, "Pw": password},
            expected=(200,),
        )
        data = response.json()
        token = data.get("AccessToken")
        if not token:
            raise SetupError(f"{self.server.label}: authentication response has no token")
        self.token = token
        user = data.get("User", {})
        self.user_id = user.get("Id")
        if not self.user_id:
            raise SetupError(f"{self.server.label}: authentication response has no user id")

    def set_server_name(self, server_name: str) -> None:
        """Update the ordinary system configuration after admin authentication."""
        configuration = self.json("GET", "/System/Configuration", authenticate=True)
        if not isinstance(configuration, dict):
            raise SetupError(f"{self.server.label}: invalid system configuration")
        configuration["ServerName"] = server_name
        self.request(
            "POST",
            "/System/Configuration",
            payload=configuration,
            authenticate=True,
        )

    def get_or_create_library(self, manifest: dict[str, Any]) -> dict[str, Any]:
        library = manifest["library"]
        existing = self.json("GET", "/Library/VirtualFolders", authenticate=True)
        if not isinstance(existing, list):
            raise SetupError(f"{self.server.label}: invalid library list response")
        matches = [item for item in existing if item.get("Name") == library["name"]]
        if len(matches) > 1:
            raise SetupError(f"{self.server.label}: duplicate seed libraries exist")
        if matches:
            match = matches[0]
            locations = sorted(match.get("Locations", []))
            expected_locations = sorted(library["paths"])
            # Repair an earlier partial seed created by a previous runner. This
            # is safe because only paths declared by the immutable manifest are
            # added; an unexpected path remains a hard failure.
            if not set(locations).issubset(expected_locations):
                raise SetupError(
                    f"{self.server.label}: existing seed library has different locations: "
                    f"{locations}"
                )
            for path in expected_locations:
                if path not in locations:
                    self.request(
                        "POST",
                        "/Library/VirtualFolders/Paths",
                        params={"refreshLibrary": "true"},
                        payload={"Name": library["name"], "Path": path},
                        authenticate=True,
                    )
            repaired = self.json("GET", "/Library/VirtualFolders", authenticate=True)
            matches = [item for item in repaired if item.get("Name") == library["name"]]
            if len(matches) != 1 or sorted(matches[0].get("Locations", [])) != expected_locations:
                raise SetupError(f"{self.server.label}: could not repair seed library paths")
            return matches[0]

        self.request(
            "POST",
            "/Library/VirtualFolders",
            params={
                "name": library["name"],
                "collectionType": library["collectionType"],
                "paths": library["paths"],
                "refreshLibrary": "true",
            },
            authenticate=True,
            payload={"LibraryOptions": library["options"]},
        )
        libraries = self.json("GET", "/Library/VirtualFolders", authenticate=True)
        matches = [item for item in libraries if item.get("Name") == library["name"]]
        if len(matches) != 1:
            raise SetupError(f"{self.server.label}: seed library was not created")
        return matches[0]

    def refresh_library(self) -> None:
        self.request("POST", "/Library/Refresh", authenticate=True)

    def seeded_items(self, library_id: str) -> list[dict[str, Any]]:
        if not self.user_id:
            raise SetupError(f"{self.server.label}: no authenticated user id is available")
        data = self.json(
            "GET",
            "/Items",
            authenticate=True,
            params={
                "ParentId": library_id,
                "UserId": self.user_id,
                "Recursive": "true",
                "IncludeItemTypes": "Audio",
                "Fields": "Path,MediaSources,DateCreated,ProviderIds",
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("Items"), list):
            raise SetupError(f"{self.server.label}: invalid /Items response")
        return data["Items"]


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"Cannot read manifest {path}: {exc}") from exc
    for key in ("files", "startup", "remoteAccess", "library"):
        if key not in manifest:
            raise SetupError(f"Manifest is missing {key}")
    if not manifest["files"]:
        raise SetupError("Manifest must contain at least one seed file")
    return manifest


def write_pcm_wave(target: Path, specification: dict[str, Any]) -> None:
    sample_rate = int(specification["sampleRateHz"])
    duration = int(specification["durationSeconds"])
    frequency = int(specification["frequencyHz"])
    channels = int(specification["channels"])
    sample_width = int(specification["sampleWidthBytes"])
    if sample_width != 2 or channels != 1 or sample_rate <= 0 or duration <= 0:
        raise SetupError("Only positive, mono, 16-bit PCM WAV seed specifications are supported")
    target.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(sample_rate * duration):
        # Use integer-safe bounded amplitude to produce byte-identical WAV fixtures.
        amplitude = int(12000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        frames.extend(struct.pack("<h", amplitude))
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_seed_media(manifest: dict[str, Any], seed_dir: Path) -> list[dict[str, str]]:
    generated: list[dict[str, str]] = []
    for specification in manifest["files"]:
        target = seed_dir / specification["relativePath"]
        write_pcm_wave(target, specification)
        generated.append(
            {
                "relativePath": specification["relativePath"],
                "sha256": sha256(target),
                "bytes": str(target.stat().st_size),
            }
        )
    return sorted(generated, key=lambda item: item["relativePath"])


def canonical_library(library: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": library.get("Name"),
        "collectionType": library.get("CollectionType"),
        "locations": sorted(library.get("Locations", [])),
        "options": {
            key: library.get("LibraryOptions", {}).get(key)
            for key in (
                "EnablePhotos",
                "EnableRealtimeMonitor",
                "EnableChapterImageExtraction",
            )
        },
    }


def canonical_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("Name"),
        "type": item.get("Type"),
        "mediaType": item.get("MediaType"),
        "path": item.get("Path"),
        "size": item.get("Size"),
        "runTimeTicks": item.get("RunTimeTicks"),
    }


def select_system_configuration(
    configuration: dict[str, Any], network_configuration: dict[str, Any]
) -> dict[str, Any]:
    keys = (
        "ServerName",
        "UICulture",
        "MetadataCountryCode",
        "PreferredMetadataLanguage",
    )
    selected = {key: configuration.get(key) for key in keys}
    selected["EnableRemoteAccess"] = network_configuration.get("EnableRemoteAccess")
    selected["EnableAutomaticPortMapping"] = network_configuration.get("EnableUPnP")
    return selected


def wait_for_seed_items(
    client: JellyfinClient, library_id: str, expected_count: int, deadline: float
) -> list[dict[str, Any]]:
    last_count = -1
    while time.monotonic() < deadline:
        items = client.seeded_items(library_id)
        if len(items) == expected_count:
            return items
        last_count = len(items)
        time.sleep(2)
    raise SetupError(
        f"{client.server.label}: scan timed out; expected {expected_count} audio items, "
        f"found {last_count}"
    )


def collect_state(
    client: JellyfinClient,
    library: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    user = client.json("GET", "/Users/Me", authenticate=True)
    configuration = client.json("GET", "/System/Configuration", authenticate=True)
    network_configuration = client.json(
        "GET", "/System/Configuration/Network", authenticate=True
    )
    public_info = client.json("GET", "/System/Info/Public")
    if (
        not isinstance(user, dict)
        or not isinstance(configuration, dict)
        or not isinstance(network_configuration, dict)
    ):
        raise SetupError(f"{client.server.label}: invalid user or system configuration")
    return {
        "startupCompleted": public_info.get("StartupWizardCompleted"),
        "configuration": select_system_configuration(configuration, network_configuration),
        "user": {
            "name": user.get("Name"),
            "isAdministrator": user.get("Policy", {}).get("IsAdministrator"),
        },
        "library": canonical_library(library),
        "items": sorted((canonical_item(item) for item in items), key=lambda item: item["name"] or ""),
    }


def validate_expected_state(
    label: str,
    state: dict[str, Any],
    manifest: dict[str, Any],
    username: str,
    expected_item_count: int,
) -> None:
    """Reject two equally wrong states before reporting them as equivalent."""
    startup = manifest["startup"]
    remote_access = manifest["remoteAccess"]
    expected_configuration = {
        "ServerName": startup["serverName"],
        "UICulture": startup["uiCulture"],
        "MetadataCountryCode": startup["metadataCountryCode"],
        "PreferredMetadataLanguage": startup["preferredMetadataLanguage"],
        "EnableRemoteAccess": remote_access["enableRemoteAccess"],
        "EnableAutomaticPortMapping": remote_access["enableAutomaticPortMapping"],
    }
    if state["startupCompleted"] is not True:
        raise SetupError(f"{label}: Setup Wizard is not marked complete")
    if state["configuration"] != expected_configuration:
        raise SetupError(
            f"{label}: server configuration does not match the G1-06 manifest: "
            f"{state['configuration']}"
        )
    if state["user"] != {"name": username, "isAdministrator": True}:
        raise SetupError(f"{label}: unexpected initial admin state: {state['user']}")
    expected_library = {
        "name": manifest["library"]["name"],
        "collectionType": manifest["library"]["collectionType"],
        "locations": sorted(manifest["library"]["paths"]),
        "options": manifest["library"]["options"],
    }
    if state["library"] != expected_library:
        raise SetupError(f"{label}: seed library does not match the manifest")
    if len(state["items"]) != expected_item_count:
        raise SetupError(
            f"{label}: expected {expected_item_count} indexed seed items, "
            f"found {len(state['items'])}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password",
        default=os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"),
        help="development credential; override with JELLYFIN_ADMIN_PASSWORD",
    )
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--ready-timeout", type=float, default=180)
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
        file_hashes = prepare_seed_media(manifest, args.seed_dir)
        expected_count = len(file_hashes)
        deadline = time.monotonic() + args.ready_timeout
        clients = [
            JellyfinClient(Server("v10.8.13", "http://localhost:8096"), args.timeout),
            JellyfinClient(Server("v10.9.0", "http://localhost:8097"), args.timeout),
        ]
        for client in clients:
            client.wait_until_healthy(deadline)
            if client.startup_configuration_is_available():
                client.complete_startup(manifest, args.username, args.password)
            client.authenticate(args.username, args.password)
            client.set_server_name(manifest["startup"]["serverName"])
            # Refresh the device token after wizard completion and a system-config
            # write. Jellyfin 10.9 can challenge the first elevated write made
            # with the token issued during the completion transition.
            client.authenticate(args.username, args.password)

        libraries = [client.get_or_create_library(manifest) for client in clients]
        for client in clients:
            client.refresh_library()
        item_lists = [
            wait_for_seed_items(client, library["ItemId"], expected_count, deadline)
            for client, library in zip(clients, libraries)
        ]
        states = [
            collect_state(client, library, items)
            for client, library, items in zip(clients, libraries, item_lists)
        ]
        for client, state in zip(clients, states):
            validate_expected_state(
                client.server.label,
                state,
                manifest,
                args.username,
                expected_count,
            )
        equivalent = states[0] == states[1]
        report = {
            "task": "G1-06",
            "status": "equivalent" if equivalent else "different",
            "seedFiles": file_hashes,
            "servers": {
                clients[0].server.label: states[0],
                clients[1].server.label: states[1],
            },
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.report}")
        if not equivalent:
            print("Initial state is not equivalent; see report for normalized state.", file=sys.stderr)
            return 2
        print("G1-06 success: normalized initial states are equivalent.")
        return 0
    except (SetupError, requests.RequestException, KeyError, OSError) as exc:
        print(f"G1-06 failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
