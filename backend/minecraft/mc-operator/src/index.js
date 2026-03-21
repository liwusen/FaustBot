const { WebSocketServer } = require("ws");
const { BotManager } = require("./bot_manager");
const { createCommandRouter } = require("./command_router");

const PORT = Number(process.env.MC_OPERATOR_PORT || 18901);

const clients = new Set();

function broadcast(message) {
	const data = JSON.stringify(message);
	for (const ws of clients) {
		if (ws.readyState === ws.OPEN) {
			ws.send(data);
		}
	}
}

const botManager = new BotManager((event_name, payload) => {
	broadcast({ type: "event", event_name, payload });
});
const routeCommand = createCommandRouter(botManager);

const wss = new WebSocketServer({ port: PORT });

wss.on("connection", (ws) => {
	clients.add(ws);
	ws.send(JSON.stringify({ type: "hello", data: { service: "mc-operator", port: PORT } }));

	ws.on("message", async (raw) => {
		let message;
		try {
			message = JSON.parse(raw.toString());
		} catch (error) {
			ws.send(JSON.stringify({ type: "command_result", ok: false, error: `Invalid JSON: ${error.message}` }));
			return;
		}

		if (message.type !== "command") {
			ws.send(JSON.stringify({ type: "command_result", request_id: message.request_id || null, ok: false, error: `Unsupported message type: ${message.type}` }));
			return;
		}

		try {
			const data = await routeCommand(message);
			ws.send(JSON.stringify({
				type: "command_result",
				request_id: message.request_id,
				ok: true,
				name: message.name,
				data,
			}));
		} catch (error) {
			ws.send(JSON.stringify({
				type: "command_result",
				request_id: message.request_id,
				ok: false,
				name: message.name,
				error: error instanceof Error ? error.message : String(error),
			}));
		}
	});

	ws.on("close", () => {
		clients.delete(ws);
	});
});

console.log(`[mc-operator] WebSocket server listening on ws://127.0.0.1:${PORT}`);
