function sanitizeEntity(entity) {
	if (!entity) return null;
	const pos = entity.position
		? [entity.position.x, entity.position.y, entity.position.z]
		: null;
	return {
		id: entity.id ?? null,
		type: entity.name || entity.displayName || entity.type || "unknown",
		kind: entity.type || "unknown",
		username: entity.username || null,
		pos,
	};
}

function collectNearbyEntities(bot, radius = 8) {
	if (!bot?.entity?.position) return [];
	const origin = bot.entity.position;
	return Object.values(bot.entities || {})
		.filter((entity) => entity && entity.position && entity.id !== bot.entity.id)
		.filter((entity) => origin.distanceTo(entity.position) <= radius)
		.map(sanitizeEntity)
		.filter(Boolean)
		.slice(0, 20);
}

function buildEventPayload(bot, extra = {}) {
	return {
		bot_username: bot?.username || null,
		health: bot?.health ?? null,
		food: bot?.food ?? null,
		position: bot?.entity?.position
			? [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z]
			: null,
		nearby_entities: collectNearbyEntities(bot),
		...extra,
	};
}

function registerBotEvents(bot, emitEvent) {
	bot.once("spawn", () => {
		emitEvent("join-mc-server", buildEventPayload(bot, { dimension: bot.game?.dimension || null }));
	});

	bot.on("health", () => {
		if (bot.health != null && bot.health < 20) {
			emitEvent("hurted", buildEventPayload(bot, { hurt_level: 20 - bot.health }));
		}
	});

	bot.on("messagestr", (message) => {
		emitEvent("mc-message", buildEventPayload(bot, { message }));
	});

	bot.on("death", () => {
		emitEvent("death", buildEventPayload(bot, {}));
	});

	bot.on("playerJoined", (player) => {
		emitEvent("player-joined", buildEventPayload(bot, { player: sanitizeEntity(player?.entity || { username: player?.username, type: "player" }) }));
	});

	bot.on("playerLeft", (player) => {
		emitEvent("player-left", buildEventPayload(bot, { player_name: player?.username || null }));
	});
}

module.exports = {
	collectNearbyEntities,
	sanitizeEntity,
	buildEventPayload,
	registerBotEvents,
};
