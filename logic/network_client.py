# -*- coding: utf-8 -*-

import urllib.request
import urllib.error
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

class NetworkClient:
    """Handles network communication with external services."""

    def __init__(self):
        # Executor for running blocking urllib requests
        self._executor = ThreadPoolExecutor(max_workers=2)

    def _validate_url_scheme(self, url: str) -> bool:
        """
        Security check: Validate that the URL scheme uses HTTP or HTTPS
        to prevent SSRF, Local File Inclusion (LFI), and non-HTTP protocol manipulation (e.g. file://, ftp://).
        """
        if not isinstance(url, str):
            return False
        cleaned_url = url.strip().lower()
        return cleaned_url.startswith("http://") or cleaned_url.startswith("https://")

    def make_sync_request(self, url: str, payload: dict) -> dict:
        """
        Synchronous HTTP request using urllib.

        Args:
            url (str): The destination URL.
            payload (dict): The JSON payload.

        Returns:
            dict: Structured response indicating success, data, or error details.
        """
        if not self._validate_url_scheme(url):
            return {
                "success": False,
                "error_type": "ValueError",
                "message": f"Security validation failed: Invalid URL scheme for '{url}'. Must start with http:// or https://"
            }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST'
        )

        try:
            # Enforce 600 seconds timeout as specified
            with urllib.request.urlopen(req, timeout=600) as response:
                response_body = response.read().decode('utf-8')
                return {"success": True, "data": json.loads(response_body)}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            return {"success": False, "error_type": "HTTPError", "status": e.code, "message": error_body}
        except urllib.error.URLError as e:
            return {"success": False, "error_type": "URLError", "message": str(e.reason)}
        except Exception as e:
            return {"success": False, "error_type": "Exception", "message": str(e)}

    def _blocking_stream_request(self, url: str, payload: dict, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        """
        Blocking HTTP request that reads SSE and puts chunks into an asyncio queue.
        This runs in a background thread.
        """
        if not self._validate_url_scheme(url):
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "success": False,
                    "error_type": "ValueError",
                    "message": f"Security validation failed: Invalid URL scheme for '{url}'. Must start with http:// or https://"
                }),
                loop
            )
            return

        payload['stream'] = True
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json; charset=utf-8',
                'Accept': 'text/event-stream'
            },
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            # Put the parsed JSON chunk into the async queue safely
                            asyncio.run_coroutine_threadsafe(queue.put({"success": True, "data": data_json}), loop)
                        except json.JSONDecodeError:
                            continue

            # Signal completion
            asyncio.run_coroutine_threadsafe(queue.put({"success": True, "done": True}), loop)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            asyncio.run_coroutine_threadsafe(
                queue.put({"success": False, "error_type": "HTTPError", "status": e.code, "message": error_body}), loop
            )
        except urllib.error.URLError as e:
            asyncio.run_coroutine_threadsafe(
                queue.put({"success": False, "error_type": "URLError", "message": str(e.reason)}), loop
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                queue.put({"success": False, "error_type": "Exception", "message": str(e)}), loop
            )

    async def stream_request(self, url: str, payload: dict):
        """
        Asynchronous generator that yields streamed chunks from the network.

        Args:
            url (str): The destination URL.
            payload (dict): The JSON payload.

        Yields:
            dict: Parsed chunk from the SSE stream or error dictionary.
        """
        loop = asyncio.get_event_loop()
        queue = asyncio.Queue()

        # Start the blocking request in a background thread
        future = loop.run_in_executor(
            self._executor,
            self._blocking_stream_request,
            url,
            payload,
            queue,
            loop
        )

        while True:
            item = await queue.get()

            if item.get("done", False):
                break

            yield item

            if not item.get("success", True):
                break
