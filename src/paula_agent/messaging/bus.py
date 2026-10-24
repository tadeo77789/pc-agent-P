"""RabbitMQ connection of the agent, running on its own thread."""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Callable

import pika
from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection
from pika.exceptions import AMQPError

from paula_agent.messaging import topology
from paula_agent.messaging.messages import Action, Event, Order, Result
from paula_agent.messaging.signing import InvalidSignature, sign, verify

log = logging.getLogger(__name__)

MAX_BUFFERED = 50


class AgentBus:
    """Consumes results and actions from the hub; publishes orders and events.

    Callbacks run on the bus thread. Publishing is safe from any thread; while
    disconnected, messages are buffered and sent after reconnecting.
    """

    def __init__(
        self,
        url: str,
        secret: str,
        on_result: Callable[[Result], None],
        on_action: Callable[[Action], None],
        *,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._params = pika.URLParameters(url)
        self._secret = secret
        self._on_result = on_result
        self._on_action = on_action
        self._reconnect_delay = reconnect_delay
        self._connection: BlockingConnection | None = None
        self._channel: BlockingChannel | None = None
        self._buffer: deque[tuple[str, bytes]] = deque(maxlen=MAX_BUFFERED)
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="agent-bus", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            connection, channel = self._connection, self._channel
        if connection is not None and channel is not None:
            try:
                connection.add_callback_threadsafe(channel.stop_consuming)
            except AMQPError:
                pass
        self._thread.join(timeout=5)

    def publish_order(self, order: Order) -> None:
        self._publish(topology.ORDER_KEY, order.to_dict())

    def publish_event(self, event: Event) -> None:
        self._publish(topology.EVENT_KEY, event.to_dict())

    # Internals

    def _publish(self, key: str, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        with self._lock:
            connection = self._connection
            if connection is None:
                self._buffer.append((key, body))
                return
        try:
            connection.add_callback_threadsafe(lambda: self._send(key, body))
        except AMQPError:
            with self._lock:
                self._buffer.append((key, body))

    def _send(self, key: str, body: bytes) -> None:
        assert self._channel is not None
        self._channel.basic_publish(
            exchange=topology.EXCHANGE,
            routing_key=key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
                headers=sign(self._secret, body),
            ),
        )

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                self._consume()
            except AMQPError as exc:
                log.warning("RabbitMQ unavailable (%s); retrying in %ss", exc, self._reconnect_delay)
            finally:
                with self._lock:
                    self._connection = self._channel = None
            self._stopping.wait(self._reconnect_delay)

    def _consume(self) -> None:
        connection = pika.BlockingConnection(self._params)
        channel = connection.channel()
        topology.declare(channel)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume("agent.results", self._handler(Result.from_dict, self._on_result))
        channel.basic_consume("agent.actions", self._handler(Action.from_dict, self._on_action))
        with self._lock:
            self._connection, self._channel = connection, channel
            pending = list(self._buffer)
            self._buffer.clear()
        for key, body in pending:
            self._send(key, body)
        log.info("Connected to RabbitMQ")
        try:
            channel.start_consuming()
        finally:
            if connection.is_open:
                connection.close()

    def _handler(self, parse, callback):
        def on_message(channel, method, properties, body: bytes) -> None:
            # Ack first: a redelivered action (e.g. shutdown) must never run twice.
            channel.basic_ack(method.delivery_tag)
            try:
                verify(self._secret, body, properties.headers)
                message = parse(json.loads(body))
            except (InvalidSignature, ValueError, KeyError) as exc:
                log.warning("Dropping invalid message on %s: %s", method.routing_key, exc)
                return
            try:
                callback(message)
            except Exception:
                log.exception("Handler failed for %s", method.routing_key)

        return on_message
