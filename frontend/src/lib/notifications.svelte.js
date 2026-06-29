import { getNotifications, markNotificationRead, markAllNotificationsRead } from './api.js';

class NotificationsState {
	unread = $state(0);
	/** @type {any[]} */
	recent = $state([]);
	ready = $state(false);

	async load() {
		try {
			const data = await getNotifications(5, 0);
			this.recent = data.items;
			this.unread = data.unread;
		} catch {
			// non-fatal
		} finally {
			this.ready = true;
		}
	}

	async markRead(id) {
		try {
			await markNotificationRead(id);
			this.recent = this.recent.map((n) =>
				n.id === id ? { ...n, read_at: new Date().toISOString() } : n
			);
			this.unread = Math.max(0, this.unread - 1);
		} catch {
			// non-fatal
		}
	}

	async markAllRead() {
		try {
			await markAllNotificationsRead();
			this.recent = this.recent.map((n) => ({ ...n, read_at: new Date().toISOString() }));
			this.unread = 0;
		} catch {
			// non-fatal
		}
	}
}

export const notifications = new NotificationsState();
