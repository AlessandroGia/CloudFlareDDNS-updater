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
import time
import logging
from time import sleep
from typing import Any, Optional, Tuple
from logging import Logger
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, asdict, replace

import requests
import dotenv


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

        zone_id: str = os.getenv("ZONE_ID")
        api_token: str = os.getenv("API_TOKEN")
        self.__DOMAINS: list[str] = os.getenv("DOMAIN").split(",")

        if not all([zone_id, api_token, self.__DOMAINS]):
            self.__logger.critical("Missing environment variables. Ensure ZONE_ID, API_TOKEN, and DOMAIN are set.")
            raise EnvironmentError("Missing environment variables.")

        self.__URL_API: str = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"

        self.__check_interval: int = self.__get_check_interval()

        self.__last_domains: dict[str, DomainInfo] = {}

        self.__session: requests.Session = requests.Session()
        self.__session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        })

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

    def __get_check_interval(self) -> int:
        interval: str = os.getenv("CHECK_INTERVAL", 300)
        try:
            return int(interval)
        except ValueError:
            self.__logger.error(f"Invalid CHECK_INTERVAL value: {interval}. Using default value of 300.")
            return 300

    def __get_public_ip(self, max_retries: int = 3, timeout_retry: int = 5) -> Optional[str]:
        for attempt in range(max_retries):
            try:
                response: requests.Response = requests.get(self.IP_CHECK_URL)
                response.raise_for_status()
                return response.text.strip()
            except requests.RequestException as e:
                self.__logger.error(f"{attempt + 1} of {max_retries} failed in retrieving public IP. Error: {e}")
                if attempt < max_retries - 1:
                    self.__logger.warning(f"Retrying in {timeout_retry} seconds...")
                    sleep(timeout_retry)
        return None

    def __get_cloudflare_record_info(self, domain: str, max_retries: int = 3, timeout_retry: int = 5) -> Tuple[Optional[str], Optional[str], ]:
        for attempt in range(max_retries):
            try:
                response: requests.Response = self.__session.get(self.__URL_API)
                response.raise_for_status()
                cloudflare_ip: str = "0.0.0.0"
                record_id: str = ""
                for record in response.json().get("result", {}):
                    if record.get("name") == domain:
                        cloudflare_ip, record_id = record.get("content"), record.get("id")
                self.__logger.info(f"Current IP configured on {domain}: {cloudflare_ip}")
                return cloudflare_ip, record_id
            except requests.RequestException as e:
                self.__logger.error(f"{attempt + 1} of {max_retries} failed in retrieving IP configured on Cloudflare. Error: {e}")
                if attempt < max_retries - 1:
                    self.__logger.warning(f"Retrying in {timeout_retry} seconds...")
                    sleep(timeout_retry)
        return None, None

    def __update_dns_record(self, domain: str, zone_id: str, new_ip: str, max_retries: int = 3, timeout_retry: int = 5) -> bool:
        data: ObjectData = ObjectData("A", domain, new_ip, 120, False)
        for attempt in range(max_retries):
            try:
                response: requests.Response = self.__session.put(self.__URL_API + f'/{zone_id}', json=asdict(data))
                response.raise_for_status()
                if response.json().get("success"):
                    self.__last_domains[domain] = replace(self.__last_domains[domain], ip=new_ip)
                    return True
                else:
                    self.__logger.error(f"{attempt + 1} of {max_retries} failed in updating DNS record. Error: {response.json()}")
            except requests.RequestException as e:
                self.__logger.error(f"{attempt + 1} of {max_retries} failed in updating DNS record. Error: {e}")
            if attempt < max_retries - 1:
                self.__logger.warning(f"Retrying in {timeout_retry} seconds...")
                sleep(timeout_retry)
        return False

    def __get_domain_info(self, domain, max_retries: int = 3, timeout_retry: int = 5) -> Optional[DomainInfo]:
        if domain not in self.__last_domains:
            ip, zone_id = self.__get_cloudflare_record_info(domain, max_retries, timeout_retry)
            if not (ip and zone_id):
                return None
            self.__last_domains[domain] = DomainInfo(ip=ip, zone_id=zone_id)
        return self.__last_domains[domain]

    def main(self) -> None:
        while True:
            for domain in (domain.strip() for domain in self.__DOMAINS):
                if domain:
                    if not (host_ip := self.__get_public_ip(max_retries=3, timeout_retry=5)):
                        self.__logger.critical("Could not retrieve public IP. Skipping update.")
                        continue
                    if not (domain_info := self.__get_domain_info(domain, max_retries=3, timeout_retry=5)):
                        self.__logger.critical(f"Could not retrieve info for {domain}. Skipping update.")
                        continue
                    if host_ip and host_ip != domain_info.ip:
                        if self.__update_dns_record(domain, domain_info.zone_id, host_ip, max_retries=3, timeout_retry=5):
                            self.__logger.info(f"{domain} successfully updated from {domain_info.ip} to {host_ip}.")
                        else:
                            self.__logger.critical(f"Could not update DNS record for {domain}. Skipping update.")
                    else:
                        self.__logger.info(f"{domain} IP has not changed.")
            time.sleep(self.__check_interval)
            self.__logger.info(f"~-~-~-~-~-~")

if __name__ == "__main__":
    dotenv.load_dotenv()
    CloudflareDDNSUpdater().main()

