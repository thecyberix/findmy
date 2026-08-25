"""Module for Anisette header providers."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import locale
import logging
import plistlib
import secrets
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Literal, NotRequired, TypedDict
from urllib.parse import urlparse

from typing_extensions import override

from findmy import util

if TYPE_CHECKING:
    from anisette import Anisette, AnisetteHeaders


logger = logging.getLogger(__name__)

_ANI_V3_CLIENT_INFO = (
    "<MacBookPro13,2> <macOS;13.1;22C65> "
    "<com.apple.AuthKit/1 (com.apple.dt.Xcode/3594.4.19)>"
)
_ANI_V3_USER_AGENT = "akd/1.0 CFNetwork/808.1.4"
_ANI_V3_LOOKUP = "https://gsa.apple.com/grandslam/GsService2/lookup"


class RemoteAnisetteMapping(TypedDict):
    """JSON mapping representing state of a remote Anisette provider."""

    type: Literal["aniRemote"]
    url: str
    # Anisette-v3 device identity (stable virtual Mac). Prefer these over headers.
    adi_pb: NotRequired[str]
    identifier: NotRequired[str]
    # Legacy v1 cache; OTP goes stale within seconds and cannot be refreshed safely.
    headers: NotRequired[dict[str, str]]


class LocalAnisetteMapping(TypedDict):
    """JSON mapping representing state of a local Anisette provider."""

    type: Literal["aniLocal"]
    prov_data: str | None


AnisetteMapping = RemoteAnisetteMapping | LocalAnisetteMapping


def get_provider_from_mapping(
    mapping: AnisetteMapping,
    *,
    libs_path: str | Path | None = None,
) -> RemoteAnisetteProvider | LocalAnisetteProvider:
    """Get the correct Anisette provider instance from saved JSON data."""
    if mapping["type"] == "aniRemote":
        return RemoteAnisetteProvider.from_json(mapping)
    if mapping["type"] == "aniLocal":
        return LocalAnisetteProvider.from_json(mapping, libs_path=libs_path)
    msg = f"Unknown anisette type: {mapping['type']}"
    raise ValueError(msg)


class BaseAnisetteProvider(util.abc.Closable, util.abc.Serializable, ABC):
    """
    Abstract base class for Anisette providers.

    Generously derived from https://github.com/nythepegasus/grandslam/blob/main/src/grandslam/gsa.py#L41.
    """

    @property
    @abstractmethod
    def otp(self) -> str:
        """A seemingly random base64 string containing 28 bytes."""
        raise NotImplementedError

    @property
    @abstractmethod
    def machine(self) -> str:
        """A base64 encoded string of 60 'random' bytes."""
        raise NotImplementedError

    @property
    def timestamp(self) -> str:
        """Current timestamp in ISO 8601 format."""
        return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat() + "Z"

    @property
    def timezone(self) -> str:
        """Abbreviation of the timezone of the device."""
        return str(datetime.now().astimezone().tzinfo)

    @property
    def locale(self) -> str:
        """Locale of the device (e.g. en_US)."""
        return locale.getdefaultlocale()[0] or "en_US"

    @property
    def router(self) -> str:
        """
        A number, either 17106176 or 50660608.

        It doesn't seem to matter which one we use.
        - 17106176 is used by Sideloadly and Provision (android) based servers.
        - 50660608 is used by Windows iCloud based servers.
        """
        return "17106176"

    @property
    def client(self) -> str:
        """
        Client string.

        The format is as follows:
        <%MODEL%> <%OS%;%MAJOR%.%MINOR%(%SPMAJOR%,%SPMINOR%);%BUILD%>
         <%AUTHKIT_BUNDLE_ID%/%AUTHKIT_VERSION% (%APP_BUNDLE_ID%/%APP_VERSION%)>

        Where:
            MODEL: The model of the device (e.g. MacBookPro15,1 or 'PC'
            OS: The OS of the device (e.g. Mac OS X or Windows)
            MAJOR: The major version of the OS (e.g. 10)
            MINOR: The minor version of the OS (e.g. 15)
            SPMAJOR: The major version of the service pack (e.g. 0) (Windows only)
            SPMINOR: The minor version of the service pack (e.g. 0) (Windows only)
            BUILD: The build number of the OS (e.g. 19C57)
            AUTHKIT_BUNDLE_ID: The bundle ID of the AuthKit framework (e.g. com.apple.AuthKit)
            AUTHKIT_VERSION: The version of the AuthKit framework (e.g. 1)
            APP_BUNDLE_ID: The bundle ID of the app (e.g. com.apple.dt.Xcode)
            APP_VERSION: The version of the app (e.g. 3594.4.19)
        """
        return (
            "<MacBookPro18,3> <Mac OS X;13.4.1;22F8> "
            "<com.apple.AOSKit/282 (com.apple.dt.Xcode/3594.4.19)>"
        )

    async def get_headers(
        self,
        user_id: str,
        device_id: str,
        serial: str = "0",
        with_client_info: bool = False,
    ) -> dict[str, str]:
        """
        Generate a complete dictionary of Anisette headers.

        Consider using :meth:`BaseAppleAccount.get_anisette_headers` instead.
        """
        headers = {
            # Current Time
            "X-Apple-I-Client-Time": self.timestamp,
            "X-Apple-I-TimeZone": self.timezone,
            # Locale
            "loc": self.locale,
            "X-Apple-Locale": self.locale,
            # 'One Time Password'
            "X-Apple-I-MD": self.otp,
            # 'Local User ID'
            "X-Apple-I-MD-LU": base64.b64encode(str(user_id).encode()).decode(),
            # 'Machine ID'
            "X-Apple-I-MD-M": self.machine,
            # 'Routing Info', some implementations convert this to an integer
            "X-Apple-I-MD-RINFO": self.router,
            # 'Device Unique Identifier'
            "X-Mme-Device-Id": str(device_id).upper(),
            # 'Device Serial Number'
            "X-Apple-I-SRL-NO": serial,
        }

        if with_client_info:
            headers["X-Mme-Client-Info"] = self.client
            headers["X-Apple-App-Info"] = "com.apple.gs.xcode.auth"
            headers["X-Xcode-Version"] = "11.2 (11B41)"

        return headers

    async def get_cpd(
        self,
        user_id: str,
        device_id: str,
        serial: str = "0",
    ) -> dict[str, str]:
        """
        Generate a complete dictionary of CPD data.

        Intended for internal use.
        """
        cpd = {
            "bootstrap": True,
            "icscrec": True,
            "pbe": False,
            "prkgen": True,
            "svct": "iCloud",
        }
        cpd.update(await self.get_headers(user_id, device_id, serial))

        return cpd


class RemoteAnisetteProvider(BaseAnisetteProvider, util.abc.Serializable[RemoteAnisetteMapping]):
    """Anisette provider using anisette-v3 (stable Mac + fresh OTP)."""

    # OTP in X-Apple-I-MD expires quickly; refresh via v3 while keeping adi_pb.
    _ANISETTE_DATA_VALID_FOR = 30

    def __init__(self, server_url: str) -> None:
        """Initialize the provider with URL to the remote server."""
        super().__init__()

        self._server_url = server_url.rstrip("/")

        self._http = util.http.HttpSession()

        self._anisette_data: dict[str, str] | None = None
        self._anisette_data_expires_at: float = 0
        self._closed = False
        self._adi_pb: str | None = None
        self._identifier: str | None = None
        self._device_id = str(uuid.uuid4()).upper()

    def _host(self) -> str:
        return urlparse(self._server_url).hostname or "ani.sidestore.io"

    def _headers_url(self) -> str:
        return f"https://{self._host()}/v3/get_headers"

    def _session_url(self) -> str:
        return f"wss://{self._host()}/v3/provisioning_session"

    @override
    def to_json(self, dst: str | Path | io.TextIOBase | None = None, /) -> RemoteAnisetteMapping:
        """See :meth:`BaseAnisetteProvider.serialize`."""
        payload: RemoteAnisetteMapping = {
            "type": "aniRemote",
            "url": self._server_url,
        }
        if self._adi_pb:
            payload["adi_pb"] = self._adi_pb
        if self._identifier:
            payload["identifier"] = self._identifier
        return util.files.save_and_return_json(payload, dst)

    @classmethod
    @override
    def from_json(
        cls, val: str | Path | io.TextIOBase | io.BufferedIOBase | RemoteAnisetteMapping
    ) -> RemoteAnisetteProvider:
        """See :meth:`BaseAnisetteProvider.deserialize`."""
        val = util.files.read_data_json(val)

        assert val["type"] == "aniRemote"

        provider = cls(val["url"])
        adi_pb = val.get("adi_pb")
        identifier = val.get("identifier")
        if isinstance(adi_pb, str) and adi_pb and isinstance(identifier, str) and identifier:
            provider._adi_pb = adi_pb
            provider._identifier = identifier
        return provider

    @property
    @override
    def otp(self) -> str:
        """See :meth:`BaseAnisetteProvider.otp`."""
        otp = (self._anisette_data or {}).get("X-Apple-I-MD")
        if otp is None:
            logger.warning("X-Apple-I-MD header not found! Returning fallback...")
        return otp or ""

    @property
    @override
    def machine(self) -> str:
        """See :meth:`BaseAnisetteProvider.machine`."""
        machine = (self._anisette_data or {}).get("X-Apple-I-MD-M")
        if machine is None:
            logger.warning("X-Apple-I-MD-M header not found! Returning fallback...")
        return machine or ""

    def _apple_provision_headers(self) -> dict[str, str]:
        identifier = self._identifier or ""
        return {
            "Content-Type": "text/x-xml-plist",
            "Accept": "*/*",
            "User-Agent": _ANI_V3_USER_AGENT,
            "X-Mme-Client-Info": _ANI_V3_CLIENT_INFO,
            "X-Apple-I-Client-Time": datetime.now(tz=timezone.utc)
            .replace(microsecond=0)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "X-Apple-I-TimeZone": str(datetime.now().astimezone().tzinfo),
            "X-Apple-Locale": locale.getdefaultlocale()[0] or "en_US",
            "X-Apple-I-MD-LU": identifier,
            "X-Mme-Device-Id": self._device_id,
            "X-Apple-I-SRL-NO": "0",
        }

    @staticmethod
    def _plist_body(req: dict[str, Any] | None = None) -> bytes:
        return plistlib.dumps({"Header": {}, "Request": req or {}})

    async def _provision_v3(self) -> None:
        """Create a private virtual Mac via anisette-v3 and persist adi_pb."""
        digest = hashlib.sha256(base64.b64encode(secrets.token_bytes(16))).hexdigest()
        self._identifier = digest
        self._device_id = str(uuid.uuid4()).upper()

        logger.info("Provisioning Anisette v3 device via %s", self._host())
        lookup = await self._http.get(
            _ANI_V3_LOOKUP,
            headers=self._apple_provision_headers(),
            auto_retry=True,
        )
        urls = lookup.plist()
        start_url = urls["urls"]["midStartProvisioning"]
        end_url = urls["urls"]["midFinishProvisioning"]

        import aiohttp

        session = await self._http._get_session()  # noqa: SLF001
        async with session.ws_connect(self._session_url(), ssl=False, heartbeat=20) as ws:
            while True:
                raw = await ws.receive()
                if raw.type in {
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                }:
                    break
                if raw.type != aiohttp.WSMsgType.TEXT:
                    continue
                msg = raw.json()
                result = msg.get("result")
                if result == "GiveIdentifier":
                    await ws.send_json({"identifier": self._identifier})
                elif result == "GiveStartProvisioningData":
                    start = await self._http.post(
                        start_url,
                        data=self._plist_body(),
                        headers=self._apple_provision_headers(),
                        auto_retry=True,
                    )
                    spim = start.plist()["Response"]["spim"]
                    await ws.send_json({"spim": spim})
                elif result == "GiveEndProvisioningData":
                    end = await self._http.post(
                        end_url,
                        data=self._plist_body({"cpim": msg["cpim"]}),
                        headers=self._apple_provision_headers(),
                        auto_retry=True,
                    )
                    response = end.plist()["Response"]
                    await ws.send_json({"tk": response["tk"], "ptm": response["ptm"]})
                elif result == "ProvisioningSuccess":
                    adi_pb = msg.get("adi_pb")
                    if not isinstance(adi_pb, str) or not adi_pb:
                        msg_err = "Anisette v3 provisioning returned empty adi_pb"
                        raise RuntimeError(msg_err)
                    self._adi_pb = adi_pb
                    logger.info("Anisette v3 provisioning succeeded")
                    return
                elif result == "Timeout":
                    msg_err = "Anisette v3 provisioning timed out"
                    raise RuntimeError(msg_err)
                else:
                    msg_err = f"Unexpected Anisette v3 message: {msg}"
                    raise RuntimeError(msg_err)

        msg_err = "Anisette v3 provisioning ended without success"
        raise RuntimeError(msg_err)

    async def _refresh_anisette_data(self) -> None:
        if not self._adi_pb or not self._identifier:
            await self._provision_v3()

        logger.info("Refreshing Anisette v3 headers from %s", self._host())
        r = await self._http.post(
            self._headers_url(),
            json={"identifier": self._identifier, "adi_pb": self._adi_pb},
            auto_retry=True,
        )
        data = r.json()
        otp = data.get("X-Apple-I-MD")
        machine = data.get("X-Apple-I-MD-M")
        if not isinstance(otp, str) or not isinstance(machine, str):
            msg = f"Unexpected Anisette v3 headers response: {data}"
            raise RuntimeError(msg)
        self._anisette_data = {
            "X-Apple-I-MD": otp,
            "X-Apple-I-MD-M": machine,
        }
        self._anisette_data_expires_at = time.time() + self._ANISETTE_DATA_VALID_FOR

    @override
    async def get_headers(
        self,
        user_id: str,
        device_id: str,
        serial: str = "0",
        with_client_info: bool = False,
    ) -> dict[str, str]:
        """See :meth:`BaseAnisetteProvider.get_headers`."""
        if self._closed:
            msg = "RemoteAnisetteProvider has been closed and cannot be used"
            raise RuntimeError(msg)

        if self._anisette_data is None or time.time() >= self._anisette_data_expires_at:
            await self._refresh_anisette_data()

        return await super().get_headers(user_id, device_id, serial, with_client_info)

    @override
    async def close(self) -> None:
        """See :meth:`AnisetteProvider.close`."""
        if self._closed:
            return  # Already closed, make it idempotent

        self._closed = True

        try:
            await self._http.close()
        except (RuntimeError, OSError, ConnectionError) as e:
            logger.warning("Error closing anisette HTTP session: %s", e)


class LocalAnisetteProvider(BaseAnisetteProvider, util.abc.Serializable[LocalAnisetteMapping]):
    """Local anisette provider using the `anisette` library."""

    def __init__(
        self,
        *,
        state_blob: BytesIO | None = None,
        libs_path: str | Path | None = None,
    ) -> None:
        """Initialize the provider."""
        super().__init__()

        if isinstance(libs_path, str):
            libs_path = Path(libs_path)

        # we do not yet initialize Anisette in order to prevent blocking the event loop,
        # since the anisette library will download the required libraries synchronously.
        self._ani: Anisette | None = None
        self._ani_data: AnisetteHeaders | None = None
        self._libs_path: Path | None = libs_path
        self._state_blob: BytesIO | None = state_blob

    @property
    def _is_new_session(self) -> bool:
        return self._state_blob is None

    async def _get_ani(self) -> Anisette:
        if self._ani is not None:
            return self._ani

        if self._libs_path is None or not self._libs_path.is_file():
            logger.info(
                "The Anisette engine will download libraries required for operation, "
                "this may take a few seconds...",
            )
        if self._libs_path is None:
            logger.info(
                "To speed up future local Anisette initializations, "
                "provide a filesystem path to load the libraries from.",
            )

        files: list[BinaryIO | Path] = []
        if self._state_blob is not None:
            files.append(self._state_blob)
        if self._libs_path is not None and self._libs_path.exists():
            files.append(self._libs_path)

        from anisette import Anisette

        loop = asyncio.get_running_loop()
        ani = await loop.run_in_executor(None, Anisette.load, *files)
        is_provisioned = await loop.run_in_executor(None, lambda: ani.is_provisioned)

        if self._libs_path is not None:
            ani.save_libs(self._libs_path)

        if not self._is_new_session and not is_provisioned:
            logger.warning(
                "The Anisette state that was loaded has not yet been provisioned. "
                "Was the previous session saved properly?",
            )

        # pre-provision to ensure that the VM has initialized
        await loop.run_in_executor(None, ani.provision)

        self._ani = ani
        return ani

    @override
    def to_json(self, dst: str | Path | io.TextIOBase | None = None, /) -> LocalAnisetteMapping:
        """See :meth:`BaseAnisetteProvider.serialize`."""
        if self._ani is None:
            # Anisette has not been called yet, so the future has not yet resolved.
            # We don't want to wait here, so we just return the original state blob.
            # If the state blob is None, this means we have a new session that has not
            # been provisioned yet, so we will not save the provisioning data.
            if self._state_blob is None:
                prov_data = None
            else:
                prov_data = base64.b64encode(self._state_blob.getvalue()).decode("utf-8")
        else:
            # Anisette has been initialized, so we can save the provisioning data.
            with BytesIO() as buf:
                self._ani.save_provisioning(buf)
                prov_data = base64.b64encode(buf.getvalue()).decode("utf-8")

        return util.files.save_and_return_json(
            {
                "type": "aniLocal",
                "prov_data": prov_data,
            },
            dst,
        )

    @classmethod
    @override
    def from_json(
        cls,
        val: str | Path | io.TextIOBase | io.BufferedIOBase | LocalAnisetteMapping,
        *,
        libs_path: str | Path | None = None,
    ) -> LocalAnisetteProvider:
        """See :meth:`BaseAnisetteProvider.deserialize`."""
        val = util.files.read_data_json(val)

        assert val["type"] == "aniLocal"

        prov_data = val["prov_data"]
        state_blob = None if prov_data is None else BytesIO(base64.b64decode(prov_data))

        return cls(state_blob=state_blob, libs_path=libs_path)

    @override
    async def get_headers(
        self,
        user_id: str,
        device_id: str,
        serial: str = "0",
        with_client_info: bool = False,
    ) -> dict[str, str]:
        """See :meth:`BaseAnisetteProvider.get_headers`."""
        ani = await self._get_ani()

        # run in executor to prevent blocking the event loop,
        # since get_data may make blocking network requests.
        loop = asyncio.get_running_loop()
        self._ani_data = await loop.run_in_executor(None, ani.get_data)

        return await super().get_headers(user_id, device_id, serial, with_client_info)

    @property
    @override
    def otp(self) -> str:
        """See :meth:`BaseAnisetteProvider.otp`."""
        machine = (self._ani_data or {}).get("X-Apple-I-MD")
        if machine is None:
            logger.warning("X-Apple-I-MD header not found! Returning fallback...")
        return machine or ""

    @property
    @override
    def machine(self) -> str:
        """See :meth:`BaseAnisetteProvider.machine`."""
        machine = (self._ani_data or {}).get("X-Apple-I-MD-M")
        if machine is None:
            logger.warning("X-Apple-I-MD-M header not found! Returning fallback...")
        return machine or ""

    @override
    async def close(self) -> None:
        """See :meth:`BaseAnisetteProvider.close`."""
