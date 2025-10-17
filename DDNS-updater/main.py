"""
MIT License

Copyright (c) 2024 Alessandro

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import os
import signal
import asyncio
import logging
from typing import Optional, Tuple
from logging import Logger
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, replace, asdict

from utils.secrets import get_secret
from utils.config import load_config

import dotenv
import httpx



@dataclass(frozen=True)
class DomainInfo:
    ip: str
    zone_id: str

@dataclass(frozen=True)
class ObjectData:
    type: str
    name: str
    content: str
    ttl: int
    proxied: bool

class CloudflareDDNSUpdater:
    IP_CHECK_URL: str = "https://api.ipify.org"

    def __init__(self) -> None:
        self.__logger: Logger = self.__setup_logging()
        self.__reload_requested = False
        signal.signal(signal.SIGHUP, self.__sighup_handler)

        zone_id: str = get_secret("ZONE_ID")
        api_token: str = get_secret("API_TOKEN")
        self.__domains: list[str] = load_config("DOMAIN_FILE").get("domains", [])

        if not all([zone_id, api_token, self.__domains]):
            self.__logger.critical("Missing environment variables. Ensure ZONE_ID, API_TOKEN, and DOMAIN are set.")
            raise EnvironmentError("Missing environment variables.")

        self.__url_api: str = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"

        self.__check_interval: int = self.__get_check_interval()

        self.__last_domains: dict[str, DomainInfo] = {}

        self.__headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }


    @staticmethod
    def __setup_logging() -> Logger:
        project_root: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dockerized: bool = os.getenv("DOCKERIZED", "FALSE").upper() == "TRUE"

        log_dir: str = '/app/logs' if dockerized else os.path.join(project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        log_handler: TimedRotatingFileHandler = TimedRotatingFileHandler(os.path.join(log_dir,'CloudflareDDNS-updater.log'), when='midnight', interval=1, backupCount=7)
        formatter: logging.Formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        logger: Logger = logging.getLogger("CloudflareDDNSUpdaterLogger")
        logger.setLevel(logging.INFO)
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        return logger

    def __reload_config(self) -> None:

        if not self.__reload_requested:
            return
        self.__reload_requested = False
        new_domains = load_config("DOMAIN_FILE").get("domains", [])
        if not new_domains:
            self.__logger.warning("Reload: No domains found in configuration after reload. Keeping existing domains.")
            return
        if set(new_domains) != set(self.__domains):
            self.__domains = new_domains
            self.__logger.info(f"Reload: Configuration reloaded. New domains: {self.__domains}")
        else:
            self.__logger.info("Reload: No changes in domains after reload.")

    def __sighup_handler(self, signum, frame) -> None:
        self.__logger.info("Received SIGHUP signal. Requesting configuration reload.")
        self.__reload_requested = True
        self.__reload_config()

    def __get_check_interval(self) -> int:
        interval: str = os.getenv("CHECK_INTERVAL", 300)
        try:
            return int(interval)
        except ValueError:
            self.__logger.error(f"Invalid CHECK_INTERVAL value: {interval}. Using default value of 300.")
            return 300

    async def __get_public_ip(self, client: httpx.AsyncClient, max_retries: int = 3, timeout_retry: int = 5) -> Optional[str]:
        for attempt in range(1, max_retries + 1):
            try:
                r = await client.get(self.IP_CHECK_URL, timeout=5.0)
                r.raise_for_status()
                return r.text.strip()
            except httpx.HTTPError as e:
                self.__logger.error(f"{attempt} of {max_retries} failed in retrieving public IP. Error: {e}")
                if attempt < max_retries:
                    self.__logger.warning(f"Retrying in {timeout_retry} seconds...")
                    await asyncio.sleep(timeout_retry)
        return None

    async def __get_cloudflare_record_info(self, client: httpx.AsyncClient, domain: str, max_retries: int = 3, timeout_retry: int = 5) -> Tuple[Optional[str], Optional[str], ]:
        for attempt in range(1, max_retries + 1):
            try:
                r = await client.get(self.__url_api, timeout=5.0)
                r.raise_for_status()
                result = r.json().get("result", [])
                for rec in result:
                    if rec.get("name") == domain and rec.get("type") == "A":
                        self.__logger.info(f"Current IP configured: {rec.get('content')}")
                        return rec.get("content"), rec.get("id")
                return None, None
            except httpx.HTTPError as e:
                self.__logger.error(f"{attempt} of {max_retries} failed in retrieving IP configured on Cloudflare. Error: {e}")
                if attempt < max_retries:
                    self.__logger.warning(f"Retrying in {timeout_retry} seconds...")
                    await asyncio.sleep(timeout_retry)
        return None, None

    async def __update_dns_record(self, client: httpx.AsyncClient, domain: str, zone_id: str, new_ip: str, max_retries: int = 3, timeout_retry: int = 5) -> bool:
        data: ObjectData = ObjectData("A", domain, new_ip, 120, False)
        url = f"{self.__url_api}/{zone_id}"
        for attempt in range(1, max_retries + 1):
            try:
                r = await client.put(url, json=asdict(data), timeout=10.0)
                r.raise_for_status()
                if r.json().get("success"):
                    self.__last_domains[domain] = replace(self.__last_domains[domain], ip=new_ip)
                    return True
                else:
                    self.__logger.error(f"{attempt} of {max_retries} failed in updating DNS record. Error: {r.text}")

            except httpx.HTTPError as e:
                self.__logger.error(f"{attempt} of {max_retries} failed in updating DNS record. Error: {e}")
            if attempt < max_retries:
                self.__logger.warning(f"Retrying in {timeout_retry} seconds...")
                await asyncio.sleep(timeout_retry)
        return False

    async def __get_domain_info(self, client: httpx.AsyncClient, domain, max_retries: int = 3, timeout_retry: int = 5) -> Optional[DomainInfo]:
        if domain not in self.__last_domains:
            ip, zone_id = await self.__get_cloudflare_record_info(client, domain, max_retries, timeout_retry)
            if not (ip and zone_id):
                return None
            self.__last_domains[domain] = DomainInfo(ip=ip, zone_id=zone_id)
        return self.__last_domains[domain]

    async def main(self) -> None:
        self.__logger.info("Starting Cloudflare DDNS Updater...")
        async with httpx.AsyncClient(headers=self.__headers, http2=True, limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)) as client:
            while True:
                for domain in (domain.strip() for domain in self.__domains):
                    if domain:
                        self.__logger.info(f" -----| {domain} |----- ")
                        if not (host_ip := await self.__get_public_ip(client, max_retries=3, timeout_retry=5)):
                            self.__logger.critical("Could not retrieve public IP. Skipping update.")
                            continue
                        if not (domain_info := await self.__get_domain_info(client, domain, max_retries=3, timeout_retry=5)):
                            self.__logger.critical(f"Could not retrieve info. Skipping update.")
                            continue
                        if host_ip and host_ip != domain_info.ip:
                            if await self.__update_dns_record(client, domain, domain_info.zone_id, host_ip, max_retries=3, timeout_retry=5):
                                self.__logger.info(f"Successfully updated from {domain_info.ip} to {host_ip}.")
                            else:
                                self.__logger.critical(f"Could not update DNS record. Skipping update.")
                        else:
                            self.__logger.info(f"IP has not changed.")
                        self.__logger.info(f" ----- {'~' * len(domain)} ----- ")
                self.__logger.info(f"|----- Waiting {self.__check_interval} seconds until next check... -----|")
                await asyncio.sleep(self.__check_interval)


if __name__ == "__main__":
    dotenv.load_dotenv()
    asyncio.run(CloudflareDDNSUpdater().main())

