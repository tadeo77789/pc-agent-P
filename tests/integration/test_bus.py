"""Round trip through a real RabbitMQ. Skipped when no broker is reachable.

Start one with: docker compose -f ../hub/deploy/docker-compose.yml up -d
"""

import json
import os
import time

import pika
import pytest

from paula_agent.messaging import topology
from paula_agent.messaging.bus import AgentBus
from paula_agent.messaging.messages import Action, Intent, Order, Source
from paula_agent.messaging.signing import sign, verify

URL = os.environ.get("RABBITMQ_URL", "amqp://paula:paula@localhost:5672/")
SECRET = "integration-secret"


def broker_available() -> bool:
    try:
        pika.BlockingConnection(pika.URLParameters(URL)).close()
        return True
    except pika.exceptions.AMQPError:
        return False


pytestmark = pytest.mark.skipif(not broker_available(), reason="RabbitMQ not reachable")


def wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_agent_receives_signed_action_and_publishes_order():
    actions: list[Action] = []
    bus = AgentBus(
        URL, SECRET, on_result=lambda r: None, on_action=actions.append, reconnect_delay=0.5
    )
    bus.start()
    try:
        connection = pika.BlockingConnection(pika.URLParameters(URL))
        channel = connection.channel()
        topology.declare(channel)
        channel.queue_purge("hub.orders")

        action = Action(order_id="o1", command="system_status", args={})
        body = json.dumps(action.to_dict()).encode()
        channel.basic_publish(
            topology.EXCHANGE,
            topology.ACTION_KEY,
            body,
            pika.BasicProperties(headers=sign(SECRET, body)),
        )
        channel.basic_publish(topology.EXCHANGE, topology.ACTION_KEY, b'{"unsigned": true}')
        assert wait_for(lambda: actions, timeout=5)
        assert actions == [action]

        bus.publish_order(
            Order(source=Source.CHAT, intent=Intent.CONVERSATION, payload={"text": "hola"})
        )

        def got_order():
            method, properties, payload = channel.basic_get("hub.orders", auto_ack=True)
            if method is None:
                return False
            verify(SECRET, payload, properties.headers)
            return json.loads(payload)["payload"]["text"] == "hola"

        assert wait_for(got_order, timeout=5)
        connection.close()
    finally:
        bus.stop()
