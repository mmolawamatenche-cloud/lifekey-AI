import { removeSubscriptionsByConnection } from './realtime-subscribers';

type RealtimeEvent = {
  body?: string | null;
};

export const realtime = async (event: RealtimeEvent) => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(event.body || '{}');
  } catch (cause) {
    console.error('LIFEKEY AI received an invalid realtime event', cause);
    return { statusCode: 400 };
  }

  if (
    typeof parsed !== 'object' ||
    parsed === null ||
    Array.isArray(parsed)
  ) {
    console.error('LIFEKEY AI received an invalid realtime event payload');
    return { statusCode: 400 };
  }

  const msg = parsed as { type?: unknown; payload?: unknown };

  if (msg.type === 'system.connected') {
    return { statusCode: 200 };
  }

  if (msg.type === 'system.disconnected') {
    const payload = msg.payload;
    const connectionId =
      typeof payload === 'object' &&
      payload !== null &&
      !Array.isArray(payload) &&
      'connection_id' in payload &&
      typeof payload.connection_id === 'string'
        ? payload.connection_id
        : undefined;

    if (connectionId) {
      await removeSubscriptionsByConnection(connectionId);
    }

    return { statusCode: 200 };
  }

  return { statusCode: 200 };
};