function normalizeCommandName(name) {
	return String(name || "").trim().toLowerCase();
}

function createCommandRouter(botManager) {
	const handlers = {
		"connect-server": (args) => botManager.connect(args),
		"disconnect-server": (args) => botManager.disconnect(args.reason),
		"get-status": () => botManager.getStatus(),
		"stop-current-action": () => botManager.stopCurrentAction(),
		"look-at-player": (args) => botManager.lookAtPlayer(args),
		"look-at-a-player": (args) => botManager.lookAtPlayer(args),
		"look-at-position": (args) => botManager.lookAtPosition(args),
		"go-to-position": (args) => botManager.goToPosition(args),
		"follow-player": (args) => botManager.followPlayer(args),
		"get-mobs-around": (args) => botManager.getMobsAround(args),
		"get-players-around": (args) => botManager.getPlayersAround(args),
		"eat-food": () => botManager.eatFood(),
		"chat": (args) => botManager.chat(args),
		"equip-item": (args) => botManager.equipItem(args),
		"hold-item": (args) => botManager.holdItem(args),
		"interact-entity": (args) => botManager.interactEntity(args),
		"attack-entity": (args) => botManager.attackEntity(args),
		"inventory-summary": () => botManager.inventorySummary(),
		"nearby-blocks": (args) => botManager.nearbyBlocks(args),
		"mine-block": (args) => botManager.mineBlock(args),
		"dig-block": (args) => botManager.digBlock(args),
		"place-block": (args) => botManager.placeBlock(args),
		"collect-item-drop": (args) => botManager.collectItemDrop(args),
		"pathfind-to-entity": (args) => botManager.followPlayer({ player_name: args.player_name, distance: args.distance ?? 2 }),
		"craft-item": (args) => botManager.craftItem(args),
		"smelt-item": (args) => botManager.smeltItem(args),
		"open-chest": (args) => botManager.openChest(args),
		"withdraw-item": (args) => botManager.withdrawItem(args),
		"deposit-item": (args) => botManager.depositItem(args),
		"use-bed": (args) => botManager.useBed(args),
		"toss-item": (args) => botManager.tossItem(args),
	};

	return async function routeCommand(message) {
		const name = normalizeCommandName(message.name);
		const handler = handlers[name];
		if (!handler) {
			throw new Error(`Unsupported Minecraft command: ${name}`);
		}
		return await handler(message.args || {});
	};
}

module.exports = {
	createCommandRouter,
};
