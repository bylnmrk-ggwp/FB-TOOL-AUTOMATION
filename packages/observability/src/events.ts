import { EventEmitter } from 'node:events';
import type { EventBus } from '@fb/application';
import type { ServerEvent, ServerEventOf, ServerEventType } from '@fb/shared';

const ALL = '*';

/**
 * In-process event bus. The whole system is one node, so a modular monolith
 * needs nothing heavier; swapping in a broker later only changes this class.
 */
export class InMemoryEventBus implements EventBus {
  private readonly emitter = new EventEmitter();

  constructor(maxListeners = 100) {
    this.emitter.setMaxListeners(maxListeners);
  }

  publish(event: ServerEvent): void {
    this.emitter.emit(ALL, event);
    this.emitter.emit(event.type, event);
  }

  subscribe(listener: (event: ServerEvent) => void): () => void {
    this.emitter.on(ALL, listener);
    return () => this.emitter.off(ALL, listener);
  }

  on<T extends ServerEventType>(type: T, listener: (event: ServerEventOf<T>) => void): () => void {
    const handler = (event: ServerEvent): void => listener(event as ServerEventOf<T>);
    this.emitter.on(type, handler);
    return () => this.emitter.off(type, handler);
  }
}
