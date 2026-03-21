const mineflayer = require("mineflayer");
const { pathfinder, goals } = require("mineflayer-pathfinder");
const { collectNearbyEntities, sanitizeEntity, buildEventPayload, registerBotEvents } = require("./event_bridge");

class BotManager {
	constructor(emitEvent) {
		this.bot = null;
		this.emitEvent = emitEvent;
		this.currentAction = null;
		this.connectionConfig = null;
	}

	ensureBot() {
		if (!this.bot) throw new Error("Minecraft bot is not connected");
		return this.bot;
	}

	async connect(config) {
		if (this.bot) {
			try {
				this.bot.quit("reconnecting");
			} catch (_) {}
			this.bot = null;
		}
		this.connectionConfig = { ...config };
		this.bot = mineflayer.createBot({
			host: config.host,
			port: Number(config.port),
			username: config.username,
			version: config.version || false,
		});
		this.bot.loadPlugin(pathfinder);
		registerBotEvents(this.bot, this.emitEvent);

		await new Promise((resolve, reject) => {
			const onSpawn = () => {
				cleanup();
				resolve();
			};
			const onError = (err) => {
				cleanup();
				reject(err instanceof Error ? err : new Error(String(err)));
			};
			const cleanup = () => {
				this.bot.removeListener("spawn", onSpawn);
				this.bot.removeListener("error", onError);
			};
			this.bot.once("spawn", onSpawn);
			this.bot.once("error", onError);
		});

		return {
			connected: true,
			username: this.bot.username,
			position: this._position(),
		};
	}

	async disconnect(reason = "disconnect requested") {
		if (!this.bot) return { disconnected: true, reason: "already disconnected" };
		this.bot.quit(reason);
		this.bot = null;
		this.currentAction = null;
		return { disconnected: true, reason };
	}

	_position() {
		const bot = this.bot;
		if (!bot?.entity?.position) return null;
		return [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z];
	}

	_playerEntity(name) {
		const bot = this.ensureBot();
		const player = bot.players?.[name];
		if (!player?.entity) throw new Error(`Player not found: ${name}`);
		return player.entity;
	}

	_findFoodItem() {
		const bot = this.ensureBot();
		return bot.inventory.items().find((item) => item.name?.includes("bread") || item.name?.includes("beef") || item.name?.includes("apple") || item.foodPoints);
	}

	_findInventoryItemByName(itemName) {
		const bot = this.ensureBot();
		return bot.inventory.items().find((item) => item.name === itemName);
	}

	_findNearbyBlockByName(blockName, maxDistance = 6) {
		const bot = this.ensureBot();
		return bot.findBlock({
			matching: (block) => block && block.name === blockName,
			maxDistance,
		});
	}

	_findNearbyBedBlock(maxDistance = 6) {
		const bot = this.ensureBot();
		return bot.findBlock({
			matching: (block) => block && block.name && block.name.includes("bed"),
			maxDistance,
		});
	}

	_resolveContainerBlock(args) {
		const bot = this.ensureBot();
		if (args.x !== undefined && args.y !== undefined && args.z !== undefined) {
			return bot.blockAt(bot.entity.position.offset(Number(args.x), Number(args.y), Number(args.z)));
		}
		const blockName = String(args.block_name || args["block-name"] || "chest");
		return this._findNearbyBlockByName(blockName, Number(args.max_distance ?? 6));
	}

	async getStatus() {
		const bot = this.bot;
		return {
			connected: !!bot,
			username: bot?.username || null,
			health: bot?.health ?? null,
			food: bot?.food ?? null,
			game_mode: bot?.game?.gameMode || null,
			dimension: bot?.game?.dimension || null,
			position: this._position(),
			current_action: this.currentAction,
			nearby_entities: bot ? collectNearbyEntities(bot) : [],
		};
	}

	async stopCurrentAction() {
		const bot = this.ensureBot();
		bot.pathfinder?.setGoal(null);
		bot.clearControlStates();
		this.currentAction = null;
		return { stopped: true };
	}

	async lookAtPlayer(args) {
		const entity = this._playerEntity(args.player_name || args["player-name"]);
		await this.ensureBot().lookAt(entity.position.offset(0, entity.height || 1.6, 0), true);
		return { looked_at: entity.username || args.player_name || args["player-name"] };
	}

	async lookAtPosition(args) {
		const bot = this.ensureBot();
		const pos = { x: Number(args.x), y: Number(args.y), z: Number(args.z) };
		await bot.lookAt(pos, true);
		return { looked_at: [pos.x, pos.y, pos.z] };
	}

	async goToPosition(args) {
		const bot = this.ensureBot();
		const goal = new goals.GoalBlock(Number(args.x), Number(args.y), Number(args.z));
		this.currentAction = { type: "go-to-position", target: [Number(args.x), Number(args.y), Number(args.z)] };
		bot.pathfinder.setGoal(goal);
		return { started: true, target: this.currentAction.target };
	}

	async followPlayer(args) {
		const bot = this.ensureBot();
		const entity = this._playerEntity(args.player_name || args["player-name"]);
		const distance = Number(args.distance ?? 2);
		this.currentAction = { type: "follow-player", player_name: entity.username || args.player_name || args["player-name"], distance };
		bot.pathfinder.setGoal(new goals.GoalFollow(entity, distance), true);
		return { started: true, target: this.currentAction.player_name, distance };
	}

	async getMobsAround(args) {
		const bot = this.ensureBot();
		const radius = Number(args.radius ?? 5);
		const origin = bot.entity.position;
		const mobs = Object.values(bot.entities || {})
			.filter((entity) => entity && entity.type === "mob" && entity.position && origin.distanceTo(entity.position) <= radius)
			.map((entity) => ({
				type: entity.name || entity.displayName || "unknown",
				"pos-x-y-z": [entity.position.x, entity.position.y, entity.position.z],
				id: entity.id,
			}));
		return { mobs };
	}

	async getPlayersAround(args) {
		const bot = this.ensureBot();
		const radius = Number(args.radius ?? 8);
		const origin = bot.entity.position;
		const players = Object.values(bot.players || {})
			.filter((player) => player?.entity && player.username !== bot.username)
			.filter((player) => origin.distanceTo(player.entity.position) <= radius)
			.map((player) => ({
				name: player.username,
				"pos-x-y-z": [player.entity.position.x, player.entity.position.y, player.entity.position.z],
				id: player.entity.id,
			}));
		return { players };
	}

	async eatFood() {
		const bot = this.ensureBot();
		const food = this._findFoodItem();
		if (!food) throw new Error("No food item found in inventory");
		await bot.equip(food, "hand");
		await bot.consume();
		return { ate: food.name };
	}

	async chat(args) {
		const bot = this.ensureBot();
		const message = String(args.message ?? "");
		bot.chat(message);
		return { sent: true, message };
	}

	async equipItem(args) {
		const bot = this.ensureBot();
		const itemName = String(args.item_name || args["item-name"] || "");
		const destination = String(args.destination || "hand");
		const item = bot.inventory.items().find((it) => it.name === itemName);
		if (!item) throw new Error(`Item not found in inventory: ${itemName}`);
		await bot.equip(item, destination);
		return { equipped: item.name, destination };
	}

	async holdItem(args) {
		return this.equipItem({ ...args, destination: "hand" });
	}

	async interactEntity(args) {
		const bot = this.ensureBot();
		const entityId = Number(args.entity_id || args["entity-id"]);
		const entity = bot.entities?.[entityId];
		if (!entity) throw new Error(`Entity not found: ${entityId}`);
		await bot.activateEntity(entity);
		return { interacted: entityId };
	}

	async attackEntity(args) {
		const bot = this.ensureBot();
		const entityId = Number(args.entity_id || args["entity-id"]);
		const entity = bot.entities?.[entityId];
		if (!entity) throw new Error(`Entity not found: ${entityId}`);
		bot.attack(entity);
		return { attacked: entityId };
	}

	async inventorySummary() {
		const bot = this.ensureBot();
		return {
			items: bot.inventory.items().map((item) => ({
				name: item.name,
				count: item.count,
				slot: item.slot,
			})),
		};
	}

	async nearbyBlocks(args) {
		const bot = this.ensureBot();
		const radius = Number(args.radius ?? 4);
		const blocks = [];
		const origin = bot.entity.position.floored();
		for (let x = -radius; x <= radius; x++) {
			for (let y = -radius; y <= radius; y++) {
				for (let z = -radius; z <= radius; z++) {
					const block = bot.blockAt(origin.offset(x, y, z));
					if (block && block.name !== "air") {
						blocks.push({ name: block.name, position: [block.position.x, block.position.y, block.position.z] });
					}
				}
			}
		}
		return { blocks: blocks.slice(0, 80) };
	}

	async mineBlock(args) {
		const bot = this.ensureBot();
		const target = bot.blockAt(bot.entity.position.offset(Number(args.x), Number(args.y), Number(args.z)));
		if (!target) throw new Error("Target block not found");
		await bot.dig(target);
		return { mined: target.name, position: [target.position.x, target.position.y, target.position.z] };
	}

	async digBlock(args) {
		return this.mineBlock(args);
	}

	async placeBlock(args) {
		const bot = this.ensureBot();
		const ref = bot.blockAt(bot.entity.position.offset(Number(args.ref_x ?? 0), Number(args.ref_y ?? -1), Number(args.ref_z ?? 0)));
		if (!ref) throw new Error("Reference block not found");
		const faceVector = { x: Number(args.face_x ?? 0), y: Number(args.face_y ?? 1), z: Number(args.face_z ?? 0) };
		await bot.placeBlock(ref, faceVector);
		return { placed: true };
	}

	async collectItemDrop(args) {
		const bot = this.ensureBot();
		const radius = Number(args.radius ?? 8);
		const origin = bot.entity.position;
		const drop = Object.values(bot.entities || {}).find((entity) => entity?.name === "item" && entity.position && origin.distanceTo(entity.position) <= radius);
		if (!drop) throw new Error("No item drop nearby");
		bot.pathfinder.setGoal(new goals.GoalNear(drop.position.x, drop.position.y, drop.position.z, 1));
		this.currentAction = { type: "collect-item-drop", entity_id: drop.id };
		return { started: true, entity_id: drop.id };
	}

	async tossItem(args) {
		const bot = this.ensureBot();
		const itemName = String(args.item_name || args["item-name"] || "");
		const count = Number(args.count ?? 1);
		const item = this._findInventoryItemByName(itemName);
		if (!item) throw new Error(`Item not found in inventory: ${itemName}`);
		await bot.toss(item.type, null, count);
		return { tossed: item.name, count };
	}

	async openChest(args) {
		const bot = this.ensureBot();
		const chestBlock = this._resolveContainerBlock(args);
		if (!chestBlock) throw new Error("Chest block not found");
		const chest = await bot.openChest(chestBlock);
		const items = chest.containerItems().map((item) => ({ name: item.name, count: item.count, slot: item.slot }));
		await chest.close();
		return {
			opened: true,
			block: chestBlock.name,
			position: [chestBlock.position.x, chestBlock.position.y, chestBlock.position.z],
			items,
		};
	}

	async withdrawItem(args) {
		const bot = this.ensureBot();
		const itemName = String(args.item_name || args["item-name"] || "");
		const count = Number(args.count ?? 1);
		const chestBlock = this._resolveContainerBlock(args);
		if (!chestBlock) throw new Error("Chest block not found");
		const chest = await bot.openChest(chestBlock);
		const item = chest.containerItems().find((it) => it.name === itemName);
		if (!item) {
			await chest.close();
			throw new Error(`Item not found in chest: ${itemName}`);
		}
		await chest.withdraw(item.type, null, count);
		await chest.close();
		return { withdrew: itemName, count };
	}

	async depositItem(args) {
		const bot = this.ensureBot();
		const itemName = String(args.item_name || args["item-name"] || "");
		const count = Number(args.count ?? 1);
		const item = this._findInventoryItemByName(itemName);
		if (!item) throw new Error(`Item not found in inventory: ${itemName}`);
		const chestBlock = this._resolveContainerBlock(args);
		if (!chestBlock) throw new Error("Chest block not found");
		const chest = await bot.openChest(chestBlock);
		await chest.deposit(item.type, null, count);
		await chest.close();
		return { deposited: itemName, count };
	}

	async craftItem(args) {
		const bot = this.ensureBot();
		const itemName = String(args.item_name || args["item-name"] || "");
		const count = Number(args.count ?? 1);
		const mcData = require("minecraft-data")(bot.version);
		const item = mcData.itemsByName[itemName];
		if (!item) throw new Error(`Unknown item: ${itemName}`);
		const recipes = bot.recipesFor(item.id, null, count, null);
		if (!recipes || recipes.length === 0) throw new Error(`No craft recipe found for: ${itemName}`);
		await bot.craft(recipes[0], count, null);
		return { crafted: itemName, count };
	}

	async smeltItem(args) {
		const bot = this.ensureBot();
		const inputName = String(args.item_name || args["item-name"] || "");
		const fuelName = String(args.fuel_name || args["fuel-name"] || "coal");
		const count = Number(args.count ?? 1);
		const furnaceBlock = this._findNearbyBlockByName(String(args.block_name || args["block-name"] || "furnace"), Number(args.max_distance ?? 6));
		if (!furnaceBlock) throw new Error("Furnace block not found nearby");
		const inputItem = this._findInventoryItemByName(inputName);
		if (!inputItem) throw new Error(`Input item not found in inventory: ${inputName}`);
		const fuelItem = this._findInventoryItemByName(fuelName);
		if (!fuelItem) throw new Error(`Fuel item not found in inventory: ${fuelName}`);
		const furnace = await bot.openFurnace(furnaceBlock);
		await furnace.putInput(inputItem.type, null, count);
		await furnace.putFuel(fuelItem.type, null, 1);
		await new Promise((resolve) => setTimeout(resolve, Number(args.wait_ms ?? 5000)));
		const output = furnace.outputItem();
		if (output) {
			await furnace.takeOutput();
		}
		await furnace.close();
		return {
			smelted_input: inputName,
			fuel: fuelName,
			output: output ? { name: output.name, count: output.count } : null,
		};
	}

	async useBed(args) {
		const bot = this.ensureBot();
		const bedBlock = this._findNearbyBedBlock(Number(args.max_distance ?? 6));
		if (!bedBlock) throw new Error("No bed found nearby");
		await bot.sleep(bedBlock);
		return {
			sleeping: true,
			position: [bedBlock.position.x, bedBlock.position.y, bedBlock.position.z],
		};
	}
}

module.exports = {
	BotManager,
	sanitizeEntity,
	buildEventPayload,
};
