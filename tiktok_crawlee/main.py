from datetime import timedelta

from apify import Actor
from crawlee.crawlers import PlaywrightCrawler
from crawlee import ConcurrencySettings
from crawlee import Request

from .routes import router


async def main() -> None:
    """The crawler entry point."""
    # When creating the template, we confirmed Apify integration.
    # However, this isn't important for us at this stage.
    async with Actor:
        # highlight-start
        actor_input = await Actor.get_input()

        max_items = actor_input.get("maxItems", 0)
        requests = [
            Request.from_url(url, user_data={"limit": max_items})
            for url in actor_input.get("urls", [])
        ]
        proxy = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get("proxySettings")
        )
        # highlight-end

        # Create a crawler with the necessary settings
        crawler = PlaywrightCrawler(
            # Limit scraping intensity by setting a limit on requests per minute
            concurrency_settings=ConcurrencySettings(max_tasks_per_minute=50),
            # We'll configure the `router` in the next step
            request_handler=router,
            # You can use `False` during development. But for production, it's always `True`
            headless=True,
            max_requests_per_crawl=100,
            # Increase the timeout for the request handling pipeline
            request_handler_timeout=timedelta(seconds=120),
            browser_type="firefox",
            # Limit any permissions to device data
            browser_new_context_options={"permissions": []},
        )

        # Run the crawler to collect data from several user pages
        await crawler.run(
            [
                Request.from_url(
                    "https://www.tiktok.com/@apifyoffice",
                    user_data={"limit": max_items},
                ),
                Request.from_url(
                    "https://www.tiktok.com/@authorbrandonsanderson",
                    user_data={"limit": max_items},
                ),
            ]
        )
