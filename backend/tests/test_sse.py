import json

from app.api.sse import format_sse


def test_format_sse_writes_event_and_json_data():
    data = {"text": 'Hi "there"\nnext'}
    assert format_sse("token", data) == "event: token\ndata: " + json.dumps(data) + "\n\n"
    assert "\n" not in json.dumps(data)  # newlines in data are escaped, so the event stays on one data line
