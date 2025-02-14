import asyncio

import pytest

import starlette

from strawberry.subscriptions.constants import (
    GQL_COMPLETE,
    GQL_CONNECTION_ACK,
    GQL_CONNECTION_INIT,
    GQL_CONNECTION_KEEP_ALIVE,
    GQL_CONNECTION_TERMINATE,
    GQL_DATA,
    GQL_ERROR,
    GQL_START,
    GQL_STOP,
    GRAPHQL_WS,
)
from tests.fixtures.utils import TickEventLoopPolicy


def test_simple_subscription(test_client):
    asyncio.set_event_loop_policy(TickEventLoopPolicy())

    with test_client.websocket_connect("/", GRAPHQL_WS) as ws:
        ws.send_json({"type": GQL_CONNECTION_INIT})
        ws.send_json(
            {
                "type": GQL_START,
                "id": "demo",
                "payload": {"query": "subscription { example }"},
            }
        )

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_ACK

        response = ws.receive_json()
        assert response["type"] == GQL_DATA
        assert response["id"] == "demo"
        assert response["payload"]["data"] == {"example": "Hi"}

        ws.send_json({"type": GQL_STOP, "id": "demo"})
        response = ws.receive_json()
        assert response["type"] == GQL_COMPLETE
        assert response["id"] == "demo"

        ws.send_json({"type": GQL_CONNECTION_TERMINATE})

        # make sure the websocket is disconnected now
        with pytest.raises(starlette.websockets.WebSocketDisconnect):
            ws.receive_json()


def test_operation_selection(test_client):
    asyncio.set_event_loop_policy(TickEventLoopPolicy())

    with test_client.websocket_connect("/", GRAPHQL_WS) as ws:
        ws.send_json({"type": GQL_CONNECTION_INIT})
        ws.send_json(
            {
                "type": GQL_START,
                "id": "demo",
                "payload": {
                    "query": """
                        subscription Subscription1 { echo(message: "Hi1") }
                        subscription Subscription2 { echo(message: "Hi2") }
                    """,
                    "operationName": "Subscription2",
                },
            }
        )

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_ACK

        response = ws.receive_json()
        assert response["type"] == GQL_DATA
        assert response["id"] == "demo"
        assert response["payload"]["data"] == {"echo": "Hi2"}

        ws.send_json({"type": GQL_STOP, "id": "demo"})
        response = ws.receive_json()
        assert response["type"] == GQL_COMPLETE
        assert response["id"] == "demo"

        ws.send_json({"type": GQL_CONNECTION_TERMINATE})

        # make sure the websocket is disconnected now
        with pytest.raises(starlette.websockets.WebSocketDisconnect):
            ws.receive_json()


def test_sends_keep_alive(test_client_keep_alive):
    asyncio.set_event_loop_policy(TickEventLoopPolicy())

    with test_client_keep_alive.websocket_connect("/", GRAPHQL_WS) as ws:
        ws.send_json({"type": GQL_CONNECTION_INIT})
        ws.send_json(
            {
                "type": GQL_START,
                "id": "demo",
                "payload": {"query": "subscription { example }"},
            }
        )

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_ACK

        # the example subscription has a delay of 1.5 seconds
        # the keep alive is set to run as soon as the subscription starts
        # and then every 2 seconds, so we should get this sequence of messages:
        # +------+---------+
        # | Time | Message |
        # +------+---------+
        # |    0 | ka      |
        # |  1.5 | data    |
        # |    2 | ka      |
        # +------+---------+

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_KEEP_ALIVE

        response = ws.receive_json()
        assert response["type"] == GQL_DATA
        assert response["id"] == "demo"
        assert response["payload"]["data"] == {"example": "Hi"}

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_KEEP_ALIVE

        response = ws.receive_json()
        assert response["type"] == GQL_COMPLETE
        assert response["id"] == "demo"

        ws.send_json({"type": GQL_CONNECTION_TERMINATE})


def test_subscription_errors(test_client):
    with test_client.websocket_connect("/", GRAPHQL_WS) as ws:
        ws.send_json({"type": GQL_CONNECTION_INIT})
        ws.send_json(
            {
                "type": GQL_START,
                "id": "demo",
                "payload": {"query": "subscription { exampleError }"},
            }
        )

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_ACK

        response = ws.receive_json()
        assert response["type"] == GQL_DATA
        assert response["id"] == "demo"
        assert response["payload"]["data"] is None
        assert response["payload"]["errors"] == [
            {"locations": None, "message": "This is an example", "path": None}
        ]

        ws.send_json({"type": GQL_STOP, "id": "demo"})
        response = ws.receive_json()
        assert response["type"] == GQL_COMPLETE
        assert response["id"] == "demo"

        ws.send_json({"type": GQL_CONNECTION_TERMINATE})

        # make sure the websocket is disconnected now
        with pytest.raises(starlette.websockets.WebSocketDisconnect):
            ws.receive_json()


def test_subscription_field_error(test_client):
    with test_client.websocket_connect("/", GRAPHQL_WS) as ws:
        ws.send_json({"type": GQL_CONNECTION_INIT})
        ws.send_json(
            {
                "type": GQL_START,
                "id": "invalid-field",
                "payload": {"query": "subscription { notASubscriptionField }"},
            }
        )

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_ACK

        response = ws.receive_json()
        assert response["type"] == GQL_ERROR
        assert response["id"] == "invalid-field"
        assert response["payload"] == {
            "locations": [{"line": 1, "column": 16}],
            "path": None,
            "message": (
                "The subscription field 'notASubscriptionField' is not defined."
            ),
        }

        ws.send_json({"type": GQL_CONNECTION_TERMINATE})

        # make sure the websocket is disconnected now
        with pytest.raises(starlette.websockets.WebSocketDisconnect):
            ws.receive_json()


def test_subscription_syntax_error(test_client):
    with test_client.websocket_connect("/", GRAPHQL_WS) as ws:
        ws.send_json({"type": GQL_CONNECTION_INIT})
        ws.send_json(
            {
                "type": GQL_START,
                "id": "syntax-error",
                "payload": {"query": "subscription { example "},
            }
        )

        response = ws.receive_json()
        assert response["type"] == GQL_CONNECTION_ACK

        response = ws.receive_json()
        assert response["type"] == GQL_ERROR
        assert response["id"] == "syntax-error"
        assert response["payload"] == {
            "locations": [{"line": 1, "column": 24}],
            "path": None,
            "message": "Syntax Error: Expected Name, found <EOF>.",
        }

        ws.send_json({"type": GQL_CONNECTION_TERMINATE})

        # make sure the websocket is disconnected now
        with pytest.raises(starlette.websockets.WebSocketDisconnect):
            ws.receive_json()
