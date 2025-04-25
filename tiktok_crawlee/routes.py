import asyncio
import json

from crawlee import Request
from crawlee.crawlers import PlaywrightCrawlingContext
from crawlee.router import Router

from playwright.async_api import Page

router = Router[PlaywrightCrawlingContext]()


# Helper function that extracts all loaded video links
async def extract_video_links(page: Page) -> list[Request]:
    links = []
    for post in await page.query_selector_all('[data-e2e="user-post-item"] a'):
        post_link = await post.get_attribute("href")
        if post_link and "/video/" in post_link:
            links.append(Request.from_url(post_link, label="video"))
    return links


# Main handler used for TikTok user pages
@router.default_handler
async def default_handler(context: PlaywrightCrawlingContext) -> None:
    """Default request handler."""
    context.log.info(f"Processing {context.request.url} ...")

    # Get the limit for video elements from `user_data`
    limit = context.request.user_data.get("limit", 10)
    if not isinstance(limit, int):
        raise ValueError("Limit must be an integer")

    # Wait until the button or at least a video loads, if the connection is slow
    check_locator = context.page.locator(
        '[data-e2e="user-post-item"], main button'
    ).first
    await check_locator.wait_for()

    # If the button loaded, click it to initiate video loading
    if button := await context.page.query_selector("main button"):
        await button.click()

    # Perform interaction with scrolling
    await context.page.press("body", "PageDown")

    # Start `infinite_scroll` as a background task
    scroll_task: asyncio.Task[None] = asyncio.create_task(context.infinite_scroll())

    # Wait until scrolling is completed or until the limit is reached
    while not scroll_task.done():
        requests = await extract_video_links(context.page)
        # If we've already reached the limit, interrupt scrolling and exit the loop
        if len(requests) >= limit:
            scroll_task.cancel()
            break
        else:
            # Switch the asynchronous context to allow other tasks to execute
            await asyncio.sleep(0.2)
    else:
        requests = await extract_video_links(context.page)

    # Limit the number of requests to the limit value
    requests = requests[:limit]

    # If the page wasn't properly processed for some reason and didn't find any links,
    # then I want to raise an error for retry
    if not requests:
        raise RuntimeError("No video links found")

    await context.add_requests(requests)


@router.handler(label="video")
async def video_handler(context: PlaywrightCrawlingContext) -> None:
    context.log.info(f"Processing video {context.request.url} ...")

    # Extract the element containing JSON with data
    json_element = await context.page.query_selector(
        "#__UNIVERSAL_DATA_FOR_REHYDRATION__"
    )
    if json_element:
        # Extract JSON and convert it to a dictionary
        text_data = await json_element.text_content()
        json_data = json.loads(text_data)

        data = json_data["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"][
            "itemStruct"
        ]

        # Create result item
        result_item = {
            "author": {
                "nickname": data["author"]["nickname"],
                "id": data["author"]["id"],
                "handle": data["author"]["uniqueId"],
                "signature": data["author"]["signature"],
                "followers": data["authorStats"]["followerCount"],
                "following": data["authorStats"]["followingCount"],
                "hearts": data["authorStats"]["heart"],
                "videos": data["authorStats"]["videoCount"],
            },
            "description": data["desc"],
            "tags": [
                item["hashtagName"] for item in data["textExtra"] if item["hashtagName"]
            ],
            "hearts": data["stats"]["diggCount"],
            "shares": data["stats"]["shareCount"],
            "comments": data["stats"]["commentCount"],
            "plays": data["stats"]["playCount"],
        }

        # Save the result to the dataset
        await context.push_data(result_item)
    else:
        # If the data wasn't received, we raise an error for retry
        raise RuntimeError("No JSON data found")
