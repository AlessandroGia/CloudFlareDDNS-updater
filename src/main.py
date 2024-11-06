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
from typing import Any, Optional
from logging import Logger
from logging.handlers import TimedRotatingFileHandler

import requests
import dotenv

class CloudflareDDNSUpdater:
    IP_CHECK_URL: str = "https://api.ipify.org"

    def __init__(self) -> None:
        self.__logger: Logger = self.__setup_logging()

        zone_id: str = os.getenv("ZONE_ID")
        record_id: str = os.getenv("RECORD_ID")
        api_token: str = os.getenv("API_TOKEN")
        self.__DOMAIN: str = os.getenv("DOMAIN")

        if not all([zone_id, record_id, api_token, self.__DOMAIN]):
            self.__logger.critical("Missing environment variables. Ensure ZONE_ID, RECORD_ID, API_TOKEN, and DOMAIN are set.")
            raise EnvironmentError("Missing environment variables.")

        self.__URL_API: str = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"

        self.__check_interval: int = self.__get_check_interval()

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

    def __get_cloudflare_ip(self) -> Optional[str]:
        try:
            response: requests.Response = self.__session.get(self.__URL_API)
            response.raise_for_status()
            cloudflare_ip = response.json().get("result", {}).get("content")
            self.__logger.info(f"Current IP configured on Cloudflare: {cloudflare_ip}")
            return cloudflare_ip
        except requests.RequestException as e:
            self.__logger.error(f"Error retrieving IP configured on Cloudflare: {e}")
            return None

    def update_dns_record(self, old_ip: str, new_ip: str) -> None:
        data: dict[str, Any] = {
            "type": "A",
            "name": self.__DOMAIN,
            "content": new_ip,
            "ttl": 120,
            "proxied": False
        }
        try:
            response: requests.Response = self.__session.put(self.__URL_API, json=data)
            response.raise_for_status()
            if response.json().get("success"):
                self.__logger.info(f"DNS record successfully updated from {old_ip} to {new_ip}")
            else:
                self.__logger.error(f"Failed to update DNS record: {response.json()}")
        except requests.RequestException as e:
            self.__logger.error(f"Error in DNS update request: {e}")

    def main(self) -> None:
        last_ip: str = self.__get_cloudflare_ip()
        while True:
            current_ip: str = self.__get_public_ip()
            if current_ip and current_ip != last_ip:
                self.update_dns_record(last_ip, current_ip)
                last_ip = current_ip
            else:
                self.__logger.info("No change in public IP.")

            time.sleep(self.__check_interval)

if __name__ == "__main__":
    dotenv.load_dotenv()
    CloudflareDDNSUpdater().main()

