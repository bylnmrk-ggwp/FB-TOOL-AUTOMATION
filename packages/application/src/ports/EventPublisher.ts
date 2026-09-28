import type { ServerEvent, ServerEventOf, ServerEventType } from '@fb/shared';

/**
 * One-way channel out of the application layer. The WebSocket server is one
 * subscriber; the log writer is another.
 */
export interface EventPublisher {
  publish(event: ServerEvent): void;
}

export interface EventSubscriber {
  subscribe(listener: (event: ServerEvent) => void): () => void;
  on<T extends ServerEventType>(type: T, listener: (event: ServerEventOf<T>) => void): () => void;
}

export type EventBus = EventPublisher & EventSubscriber;
