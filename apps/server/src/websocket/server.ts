import type { FastifyInstance } from 'fastify';
import websocket from '@fastify/websocket';
import { createId, nowIso, WEBSOCKET_PATH } from '@fb/shared';
import type { Container } from '../bootstrap/container.js';
import { SERVER_VERSION } from '../config/version.js';
import { decodeClientMessage, encodeEvent } from './events.js';

/**
 * One socket per browser tab, and every domain event is broadcast to all of
 * them.
 *
 * The socket is a notification channel, not a data source: a client that
 * misses a frame still has the REST endpoints, so there is no replay buffer
 * and no per-client queue to get out of step.
 */
export const registerWebSocket = async (
  app: FastifyInstance,
  container: Container,
): Promise<void> => {
  await app.register(websocket);

  const clients = new Map<string, { send: (payload: string) => void }>();

  const unsubscribe = container.events.subscribe((event) => {
    const payload = encodeEvent(event);
    if (payload === null) {
      container.logger.warn('Refused to send an event that failed its own schema', {
        event: 'websocket.invalid_event',
        type: event.type,
      });
      return;
    }

    for (const [clientId, client] of clients) {
      try {
        client.send(payload);
      } catch {
        // A socket that cannot be written to is already gone; the close
        // handler removes it.
        clients.delete(clientId);
      }
    }
  });

  app.addHook('onClose', () => {
    unsubscribe();
    clients.clear();
  });

  app.get(WEBSOCKET_PATH, { websocket: true }, (socket) => {
    const clientId = createId('cli');
    clients.set(clientId, { send: (payload) => socket.send(payload) });

    container.logger.debug('WebSocket client connected', {
      event: 'websocket.connected',
      clientId,
      clients: clients.size,
    });

    const ready = encodeEvent({
      type: 'connection.ready',
      timestamp: nowIso(),
      payload: { clientId, serverVersion: SERVER_VERSION },
    });
    if (ready !== null) socket.send(ready);

    socket.on('message', (raw: Buffer) => {
      const message = decodeClientMessage(raw.toString());
      if (!message.success) {
        container.logger.debug('Ignored an unreadable client frame', {
          event: 'websocket.bad_frame',
          clientId,
        });
        return;
      }

      // `ping` is the only message that needs an answer; `subscribe` is
      // accepted and ignored until there is more than one topic to filter on.
      if (message.data.type === 'ping') socket.send(JSON.stringify({ type: 'pong' }));
    });

    socket.on('close', () => {
      clients.delete(clientId);
      container.logger.debug('WebSocket client disconnected', {
        event: 'websocket.disconnected',
        clientId,
        clients: clients.size,
      });
    });
  });
};
