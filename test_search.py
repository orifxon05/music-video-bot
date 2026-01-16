import asyncio
from youtubesearchpython import VideosSearch

async def test_search():
    query = "sevdim"
    print(f"Searching for: {query}")
    search = VideosSearch(query, limit=5)
    result = search.result()
    print(f"Results: {result}")

if __name__ == "__main__":
    asyncio.run(test_search())
