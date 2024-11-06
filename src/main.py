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
from typing import Any, Optional, Tuple
from logging import Logger
from logging.handlers import TimedRotatingFileHandler

import requests
import dotenv

class CloudflareDDNSUpdater:
    IP_CHECK_URL: str = "https://api.ipify.org"

    def __init__(self) -> None:
        self.__logger: Logger = self.__setup_logging()

        zone_id: str = os.getenv("ZONE_ID")
        api_token: str = os.getenv("API_TOKEN")
        self.__DOMAINS: str = os.getenv("DOMAIN").split(" ")

        if not all([zone_id, api_token, self.__DOMAINS]):
            self.__logger.critical("Missing environment variables. Ensure ZONE_ID, RECORD_ID, API_TOKEN, and DOMAIN are set.")
            raise EnvironmentError("Missing environment variables.")

        self.__URL_API: str = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"

        self.__check_interval: int = self.__get_check_interval()

        self.__last_domains: dict[str, dict[str, str]] = {}

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

    def __get_public_ip(self) -> Optional[str]:
        try:
            response: requests.Response = requests.get(self.IP_CHECK_URL)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as e:
            self.__logger.error(f"Error retrieving public IP: {e}")
            return None

    def __get_cloudflare_record_info(self, domain: str) -> Tuple[Optional[str], Optional[str]]:
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
            self.__logger.error(f"Error retrieving IP configured on Cloudflare: {e}")
            return None, None

    def update_dns_record(self, domain: str, zone_id: str, old_ip: str, new_ip: str) -> None:
        data: dict[str, Any] = {
            "type": "A",
            "name": domain,
            "content": new_ip,
            "ttl": 120,
            "proxied": False
        }
        try:
            response: requests.Response = self.__session.put(self.__URL_API + f'/{zone_id}', json=data)
            response.raise_for_status()
            if response.json().get("success"):
                self.__logger.info(f"{domain} successfully updated from {old_ip} to {new_ip}")
            else:
                self.__logger.error(f"Failed to update {domain}: {response.json()}")
        except requests.RequestException as e:
            self.__logger.error(f"Error in DNS update request: {e}")

    def get_domain_info(self, domain) -> dict[str, str]:
        if domain not in self.__last_domains:
            ip, zone_id = self.__get_cloudflare_record_info(domain)
            self.__last_domains[domain] = {"ip": ip, "zone_id": zone_id}
        return self.__last_domains[domain]

    def has_to_update(self, dns_ip: str) -> str:
        current_ip: str = self.__get_public_ip()
        if current_ip and current_ip != dns_ip:
            return current_ip
        return ""

    def main(self) -> None:
        while True:
            for domain in self.__DOMAINS:
                domain = domain.strip()
                if domain:
                    domain_info = self.get_domain_info(domain)
                    if current_ip := self.has_to_update(domain_info["ip"]):
                        self.update_dns_record(domain, domain_info["zone_id"], domain_info["ip"], current_ip)
                        self.__last_domains[domain]["ip"] = current_ip
                    else:
                        self.__logger.info(f"{domain} IP has not changed.")
            time.sleep(self.__check_interval)

if __name__ == "__main__":
    dotenv.load_dotenv()
    CloudflareDDNSUpdater().main()

