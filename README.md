
# CloudflareDDNS-updater

CloudflareDDNS-updater is a Python script that automatically updates DNS records on Cloudflare with the current public IP address. This is useful for Dynamic DNS (DDNS) configurations where the IP address changes frequently, allowing you to keep DNS records up-to-date without manual intervention.

## Features
- Automatically updates DNS records on Cloudflare with the current public IP address.
- Detailed logging with daily log rotation.
- Configurable via environment variables.

## Requirements
- Python 3.8 or higher
- A Cloudflare account with permissions to manage DNS records for the domain.

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AlessandroGia/CloudFlareDDNS-updater.git
   cd CloudflareDDNS-updater
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   4. **Create a `.env` file** in the project’s root directory with the following environment variables:

      ```dotenv
      ZONE_ID=<your ZONE_ID>
      API_TOKEN=<your API_TOKEN>
      DOMAIN=<your domains or subdomains diveded by commas>
      TZ=<your timezone> # defaults to Europe/Rome
      CHECK_INTERVAL=300  # optional, in seconds, defaults to 300
      ```

      - **ZONE_ID**: The Cloudflare Zone ID for the DNS.
      - **API_TOKEN**: The Cloudflare API token with permissions to modify DNS records.
      - **DOMAIN**: Domains or subdomains to update divided by commas.
      - **TZ**: The timezone to use for logging. A list of valid timezones can be found [here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).
      - **CHECK_INTERVAL**: (Optional) The interval in seconds to check and update the IP. Defaults to 300 seconds (5 minutes).

## Usage with Docker

Configure Docker to handle environment variables automatically with Docker Compose. Do not copy `.env` into the container manually.

### 1. Build and Run with Docker Compose

Use Docker Compose to build and start the container:

```bash
docker-compose up -d
```

### 2. Stop the Service

To stop the service, use:

```bash
docker-compose down
```

## Logging

The script generates detailed logs in `logs/CloudflareDDNS-updater.log`. Logs include information on DNS updates and any errors encountered. Logs are rotated daily, and the script retains logs from the past 7 days.

## Common Issues

- **EnvironmentError**: Raised if critical environment variables are missing. Ensure `ZONE_ID`, `API_TOKEN`, and `DOMAIN` are correctly set in the `.env` file.
- **RequestException**: An error related to HTTP requests, usually caused by network issues or invalid API credentials.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

This project uses [api.ipify.org](https://api.ipify.org) to retrieve the public IP address. 
