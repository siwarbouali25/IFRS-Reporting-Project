"""
Optional smoke test for the configured Azure fast deployment.

Run from the backend folder after activating the virtual environment:

    python test_assistant_azure_fast.py

It tests:
1. a normal REST completion;
2. a genuine SSE completion.

It does not access Django models or assistant tools.
"""

from assistant.llm import (
    _request_json,
    stream_chat_with_tools,
)

MESSAGES = [
    {
        "role": "user",
        "content": (
            "Reply with exactly these three words: "
            "Azure stream works"
        ),
    }
]


print("Normal request:")
normal = _request_json(
    messages=MESSAGES,
    tools=None,
    max_output_tokens=40,
    request_label="Azure fast smoke test",
)
print(
    normal["choices"][0]["message"]["content"]
)

print("\nStreaming request:")
for event in stream_chat_with_tools(
    MESSAGES,
    tools=[],
):
    if event["type"] == "content_delta":
        print(
            event["text"],
            end="",
            flush=True,
        )
    elif event["type"] == "complete":
        print(
            "\nSSE used:",
            event.get("sse"),
        )
